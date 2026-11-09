const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const FirestoreWallet = require('./users');
const { GameEngine } = require('./gameroom');
const admin = require('firebase-admin');

const BOT_TOKEN = process.env.BOT_TOKEN;
if (!BOT_TOKEN) throw new Error('BOT_TOKEN environment variable is required');
const BOT_CHANNEL_ID = process.env.BOT_CHANNEL_ID || '-1004418660495';

const secretCandidates = [
    process.env.FIREBASE_KEY_PATH,
    '/etc/secrets/firebase_key.json',
    path.join(__dirname, 'firebase_key.json')
].filter(Boolean);

const firebaseKeyPath = secretCandidates.find(candidate => fs.existsSync(candidate));

if (!firebaseKeyPath) {
    throw new Error('Firebase service account file not found. Set FIREBASE_KEY_PATH or mount firebase_key.json at /etc/secrets/firebase_key.json');
}

if (!admin.apps.length) {
    admin.initializeApp({
        credential: admin.credential.cert(require(firebaseKeyPath))
    });
}

const { getFirestore } = require('firebase-admin/firestore');
const db = getFirestore(admin.app(), process.env.FIRESTORE_DATABASE_ID || 'litebingo');
const app = express();

app.use(cors());
app.use(express.json({ limit: '100kb' }));

// Validate Telegram Mini App initData on the server; never trust a userId sent by the browser.
function verifyTelegramInitData(initData) {
    if (!initData || typeof initData !== 'string') return null;

    const params = new URLSearchParams(initData);
    const hash = params.get('hash');
    const authDate = Number(params.get('auth_date'));

    if (!hash || !Number.isFinite(authDate)) return null;

    const now = Math.floor(Date.now() / 1000);
    if (authDate > now + 60 || now - authDate > 86400) return null;

    const pairs = [];

    for (const [key, value] of params.entries()) {
        if (key !== 'hash') pairs.push(`${key}=${value}`);
    }

    pairs.sort();

    const dataCheckString = pairs.join('\n');
    const secretKey = crypto.createHmac('sha256', 'WebAppData').update(BOT_TOKEN).digest();
    const calculated = crypto.createHmac('sha256', secretKey).update(dataCheckString).digest();

    let supplied;

    try {
        supplied = Buffer.from(hash, 'hex');
    } catch (_) {
        return null;
    }

    if (supplied.length !== calculated.length || !crypto.timingSafeEqual(supplied, calculated)) {
        return null;
    }

    try {
        const user = JSON.parse(params.get('user') || 'null');
        if (!user || !user.id) return null;
        return user;
    } catch (_) {
        return null;
    }
}

const membershipCache = new Map();
const membershipChecks = new Map();
const MEMBERSHIP_CACHE_MS = 30 * 1000;

async function isChannelMember(userId) {
    const uid = String(userId);
    const cached = membershipCache.get(uid);

    if (cached && Date.now() - cached.at < MEMBERSHIP_CACHE_MS) {
        return cached.joined;
    }

    if (membershipChecks.has(uid)) {
        return membershipChecks.get(uid);
    }

    const check = (async () => {
        const member = await bot.telegram.getChatMember(BOT_CHANNEL_ID, uid);
        const joined =
            ['creator', 'administrator', 'member'].includes(member.status) ||
            (member.status === 'restricted' && member.is_member === true);

        membershipCache.set(uid, { joined, at: Date.now() });
        return joined;
    })();

    membershipChecks.set(uid, check);
    try {
        return await check;
    } finally {
        membershipChecks.delete(uid);
    }
}

async function requireTelegramUser(req, res, next) {
    const user = verifyTelegramInitData(req.get('X-Telegram-Init-Data'));

    if (!user) {
        return res.status(401).json({
            status: 'error',
            message: 'Open this game from the Telegram bot to authenticate.'
        });
    }

    req.telegramUser = user;
    req.telegramUserId = String(user.id);

    if (BOT_CHANNEL_ID) {
        try {
            const joined = await isChannelMember(user.id);

            if (!joined) {
                return res.status(403).json({
                    status: 'error',
                    message: 'Join the required Telegram channel first.'
                });
            }
        } catch (e) {
            console.error('API channel membership check failed:', e.message);

            return res.status(503).json({
                status: 'error',
                message: 'Could not verify channel membership.'
            });
        }
    }

    next();
}

const wallet = new FirestoreWallet(db, admin.firestore);
const engine = new GameEngine(wallet, 2);

// Recover interrupted paid rounds before accepting new game activity.
wallet.recover_unsettled()
    .then(() => engine.start())
    .catch(error => {
        console.error('Game recovery failed; engine was not started:', error);
        process.exit(1);
    });

app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

app.get('/health', (req, res) => {
    res.json({ status: 'ok' });
});

app.use('/api', requireTelegramUser);

app.get('/api/round', (req, res) => {
    res.json({
        status: 'success',
        state: engine.get_state(req.telegramUserId)
    });
});

app.post('/api/round/pick', async (req, res) => {
    const { cartel } = req.body || {};

    const [ok, code] = await engine.pick(req.telegramUserId, Number(cartel));

    res.json({
        status: ok ? 'success' : 'error',
        code,
        state: engine.get_state(req.telegramUserId)
    });
});

app.post('/api/round/unpick', (req, res) => {
    const { cartel } = req.body || {};

    const [ok, code] = engine.unpick(req.telegramUserId, Number(cartel));

    res.json({
        status: ok ? 'success' : 'error',
        code,
        state: engine.get_state(req.telegramUserId)
    });
});

app.get('/api/user-data', async (req, res) => {
    try {
        const doc = await db.collection('users').doc(req.telegramUserId).get();
        const data = doc.exists ? doc.data() : {};

        res.json({
            status: 'success',
            balance: Number(data.balance || 0),
            bonus: Number(data.bonus || 0),
            transactions: data.transactions || [],
            phone_number: data.phone_number,
            first_name: data.first_name,
            total_games_played: data.total_games_played || 0,
            total_winnings: data.total_winnings || 0,
            has_deposited: Boolean(data.has_deposited),
            referral_count: Number(data.referral_count || 0)
        });
    } catch (e) {
        console.error('user-data error:', e);

        res.status(500).json({
            status: 'error',
            message: 'Could not load user data.'
        });
    }
});

app.get('/api/leaderboard', async (req, res) => {
    try {
        const snapshot = await db.collection('users')
            .orderBy('weekly_cartels', 'desc')
            .limit(10)
            .get();

        const leaderboard = snapshot.docs.map(doc => {
            const data = doc.data();

            return {
                name: data.username || data.first_name || 'Player',
                cartels: Number(data.weekly_cartels || 0)
            };
        });

        res.json({
            status: 'success',
            leaderboard
        });
    } catch (e) {
        console.error('leaderboard error:', e);

        res.status(500).json({
            status: 'error',
            leaderboard: []
        });
    }
});

app.get('/api/referral-link', async (req, res) => {
    try {
        const me = await bot.telegram.getMe();

        res.json({
            status: 'success',
            url: `https://t.me/${me.username}?start=ref_${req.telegramUserId}`
        });
    } catch (e) {
        console.error('referral-link error:', e);
        res.status(502).json({ status: 'error' });
    }
});

app.post('/api/send-support', async (req, res) => {
    try {
        await bot.telegram.sendMessage(
            req.telegramUserId,
            '🎧 እርዳታ ለማግኘት @zeid369 ያነጋግሩ።'
        );

        res.json({ status: 'success' });
    } catch (e) {
        console.error('send-support error:', e);

        res.status(502).json({
            status: 'error',
            message: 'Could not send support message.'
        });
    }
});

app.post('/api/send-rules', async (req, res) => {
    const rules = [
        '🎮 የBingo ጨዋታ ህጎች',
        '• በአንድ ዙር እስከ 4 ካርቴል መምረጥ ይችላሉ።',
        '• የአንድ ካርቴል ዋጋ 10 ETB ነው።',
        '• ዙሩ ለመጀመር ቢያንስ 2 ተጫዋቾች ያስፈልጋሉ።',
        '• በካርድዎ ላይ አግድም፣ ቁም ወይም ሰያፍ መስመር ሲሞላ Bingo ያሸንፋሉ።',
        '• የሽልማት ገንዘብ በአሸናፊዎች መካከል ይከፈላል።'
    ].join('\n');

    try {
        await bot.telegram.sendMessage(req.telegramUserId, rules);
        res.json({ status: 'success' });
    } catch (e) {
        console.error('send-rules error:', e);

        res.status(502).json({
            status: 'error',
            message: 'Could not send game rules.'
        });
    }
});

const PORT = process.env.PORT || 5500;

const server = app.listen(PORT, () => {
    console.log(`WebApp API running on port ${PORT}`);
});

const bot = require('./bot');

module.exports = { app, engine, wallet, server };
