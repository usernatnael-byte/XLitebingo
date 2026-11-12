const express = require('express');
const cors = require('cors');
const path = require('path');
const crypto = require('crypto');
const FirestoreWallet = require('./users');
const { GameEngine } = require('./gameroom');
const { admin, db } = require('./firebase');

const BOT_TOKEN = process.env.BOT_TOKEN;
if (!BOT_TOKEN) throw new Error('BOT_TOKEN environment variable is required');
const BOT_CHANNEL_ID = process.env.BOT_CHANNEL_ID || '-1004418660495';

const app = express();

app.use(cors());
app.use(express.json({ limit: '10mb' }));

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
    const userDoc = await db.collection('users').doc(req.telegramUserId).get();
    if (userDoc.exists && userDoc.data().blocked) return res.status(403).json({status:'error',message:'Account is blocked.'});

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

const wallet = new FirestoreWallet(db);
const engine = new GameEngine(wallet, 2);

db.collection('settings').doc('bot_settings').get().then(doc => {
    if (doc.exists) {
        engine.setBotSettings(doc.data());
    }
}).catch(err => console.warn('Could not load bot settings at startup:', err));

wallet.recover_unsettled()
    .then(() => engine.start())
    .catch(error => {
        console.error('Game recovery failed; engine was not started:', error);
        process.exit(1);
    });

app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

app.get('/admin', (req, res) => res.sendFile(path.join(__dirname, 'admin.html')));

app.get('/health', (req, res) => {
    res.json({ status: 'ok' });
});

app.use('/api', requireTelegramUser);

const DEPOSIT_MINIMUM = Math.max(100, Number(process.env.DEPOSIT_MINIMUM_ETB || 100));
const WITHDRAW_MINIMUM = Math.max(100, Number(process.env.WITHDRAW_MINIMUM_ETB || 100));
// የተደራረበውን ችግር ለማጥፋት የቴሌብር መረጃዎችን በአንድ ቦታ በግልጽ ማስቀመጥ
const TELEBIRR_NAME = 'እስራኤል';
const TELEBIRR_NUMBER = '0949196145';
const DEPOSIT_INSTRUCTIONS = `💳 በቴሌብር ብቻ ገንዘብ ያስገቡ\n\nየቴሌብር ስም: ${TELEBIRR_NAME}\nስልክ ቁጥር: ${TELEBIRR_NUMBER}`;
const ADMIN_IDS = new Set([...(process.env.ADMIN_ID || '7396414604').split(','), ...(process.env.ADMIN_IDS || '').split(',')].map(v => v.trim()).filter(Boolean));

app.get('/api/wallet/history', async (req,res) => {
    try {
        const userId = String(req.telegramUserId);
        const userSnap = await db.collection('users').doc(userId).get();
        const user = userSnap.exists ? userSnap.data() : {};
        const [deposits, withdrawals] = await Promise.all([
            db.collection('deposit_requests').get(),
            db.collection('withdrawal_requests').get()
        ]);
        const requestIds = new Set();
        const items = [];
        const toIso = value => {
            const d = new Date(typeof value === 'number' || (typeof value === 'string' && /^\d+$/.test(value)) ? Number(value) : (value || Date.now()));
            return Number.isNaN(d.getTime()) ? new Date().toISOString() : d.toISOString();
        };
        for (const doc of deposits.docs) {
            const r = doc.data();
            if (String(r.user_id) !== userId) continue;
            requestIds.add(doc.id);
            items.push({id:doc.id, type:'deposit', amount:Number(r.amount||0), reference:r.reference||'', status:r.status||'pending', timestamp:r.created_at_iso || toIso(r.created_at), wallet:'bonus'});
        }
        for (const doc of withdrawals.docs) {
            const r = doc.data();
            if (String(r.user_id) !== userId) continue;
            requestIds.add(doc.id);
            items.push({id:doc.id, type:'withdrawal', amount:Number(r.amount||0), reference:doc.id, status:r.status||'pending', timestamp:toIso(r.created_at), wallet:'main'});
        }
        for (const t of (Array.isArray(user.transactions) ? user.transactions : [])) {
            if (t.request_id && requestIds.has(String(t.request_id))) continue;
            const raw = t.timestamp || t.created_at || Date.now();
            items.push({id:t.request_id || `${t.type}-${raw}`, type:t.type||'transaction', amount:Number(t.amount||0), status:t.status || 'approved', timestamp:typeof raw==='number'?new Date(raw).toISOString():raw, wallet:t.wallet || 'main'});
        }
        items.sort((a,b)=>Date.parse(b.timestamp)-Date.parse(a.timestamp));
        res.json({status:'success', transactions:items.slice(0,200)});
    } catch(e) { console.error('wallet history failed',e); res.status(500).json({status:'error',message:'Could not load transaction history.'}); }
});

app.get('/api/wallet/config', async (req,res) => {
    try {
        const snap=await db.collection('users').doc(req.telegramUserId).get();
        const u=snap.exists?snap.data():{};
        res.json({status:'success',depositMinimum:DEPOSIT_MINIMUM,withdrawMinimum:WITHDRAW_MINIMUM,telebirrName:TELEBIRR_NAME,telebirrNumber:TELEBIRR_NUMBER,depositInstructions:DEPOSIT_INSTRUCTIONS,mainBalance:Number(u.balance||0),bonusBalance:Number(u.bonus||0)});
    } catch(e) { console.error('wallet config failed',e); res.status(500).json({status:'error',message:'Wallet details unavailable.'}); }
});

app.post('/api/wallet/deposit', async (req,res) => {
    const amount=Number(req.body?.amount);
    const reference=String(req.body?.reference||'').trim().slice(0,120);
    const image=String(req.body?.imageBase64||'');
    if(!Number.isFinite(amount)||amount<DEPOSIT_MINIMUM||amount>1000000) return res.status(400).json({status:'error',message:`Minimum deposit is ${DEPOSIT_MINIMUM} ETB.`});
    if(!reference&&!image) return res.status(400).json({status:'error',message:'Enter payment reference or upload receipt.'});
    let receipt='';
    if(image){const m=image.match(/^data:image\/(jpeg|jpg|png|webp);base64,([A-Za-z0-9+/=]+)$/i);if(!m)return res.status(400).json({status:'error',message:'Receipt must be JPG, PNG or WEBP.'});const b=Buffer.from(m[2],'base64');if(b.length>4*1024*1024)return res.status(400).json({status:'error',message:'Receipt must be 4 MB or smaller.'});receipt=image;}
    try {
        const ref=db.collection('deposit_requests').doc();
        await ref.set({user_id:req.telegramUserId,amount,reference,receipt_image:receipt,status:'pending',created_at:Date.now(),created_at_iso:new Date().toISOString()});
        for(const aid of ADMIN_IDS) await bot.telegram.sendMessage(aid,`📥 Deposit request\nUser: ${req.telegramUserId}\nAmount: ${amount.toFixed(2)} ETB\nPayment reference: ${reference||'Receipt attached'}\nRequest ID: ${ref.id}`).catch(()=>{});
        await bot.telegram.sendMessage(req.telegramUserId,`⏳ DEPOSIT PENDING\n\nAmount: ${amount.toFixed(2)} ETB\nPayment Reference: ${reference||'Receipt attached'}\nRequest ID: ${ref.id}\n\nAdmin ክፍያውን እያረጋገጠ ነው። ሲጸድቅ Bonus Balance ላይ ይጨመራል።`).catch(e=>console.warn('deposit pending notification failed:',e.message));
        res.json({status:'success',message:'Deposit request sent to admin.',requestId:ref.id});
    } catch(e){console.error('deposit request failed',e);res.status(500).json({status:'error',message:'Could not submit deposit request.'});}
});

app.post('/api/wallet/withdraw', async (req,res) => {
    const amount=Number(req.body?.amount), name=String(req.body?.name||'').trim().slice(0,100), account=String(req.body?.account||'').replace(/\s/g,'').slice(0,30);
    if(!Number.isFinite(amount)||amount<WITHDRAW_MINIMUM||amount>1000000) return res.status(400).json({status:'error',message:`Minimum withdrawal is ${WITHDRAW_MINIMUM} ETB.`});
    if(name.length<2||!/^[0-9+]{9,15}$/.test(account)) return res.status(400).json({status:'error',message:'Enter valid Telebirr name and phone number.'});
    try {
        const userRef=db.collection('users').doc(req.telegramUserId), ref=db.collection('withdrawal_requests').doc();
        
        // 👉 እዚህ ጋር ያስገባኸውን ትራንዛክሽን በትክክል አስገብተነዋል
        await db.runTransaction(async tx=>{
            const us=await tx.get(userRef);
            if(!us.exists) throw new Error('USER_NOT_FOUND');
            const u=us.data();
            
            // 🛑 ዊዝድሮው ለማድረግ ዲፖዚት ማድረግ እና ዲፖዚት ካደረጉ በኋላ ቢያንስ 1 ጌም ማሸነፍ ግዴታ ነው
            if(!u.has_deposited) throw new Error('DEPOSIT_REQUIRED');
            if(!u.won_after_deposit) throw new Error('WIN_AFTER_DEPOSIT_REQUIRED');

            const balance=Number(u.balance||0);
            if(balance<amount) throw new Error('INSUFFICIENT_BALANCE');
            
            const txs=Array.isArray(u.transactions)?u.transactions:[];
            tx.update(userRef,{balance:balance-amount,transactions:[...txs,{type:'withdrawal_pending',amount,request_id:ref.id,timestamp:new Date().toISOString()}]});
            tx.set(ref,{user_id:req.telegramUserId,amount,payout_name:name,payout_account:account,status:'pending',created_at:Date.now()});
        });

        for(const aid of ADMIN_IDS) await bot.telegram.sendMessage(aid,`📤 Withdrawal request\nUser: ${req.telegramUserId}\nName: ${name}\nTelebirr: ${account}\nAmount: ${amount.toFixed(2)} ETB\nRequest ID: ${ref.id}`).catch(()=>{});
        await bot.telegram.sendMessage(req.telegramUserId,`⏳ WITHDRAWAL PENDING\n\nAmount: ${amount.toFixed(2)} ETB\nRequest ID: ${ref.id}\nStatus: PENDING\n\nAdmin ጥያቄዎን እያየ ነው። ሲጸድቅ በTelebirr ክፍያው ይፈጸማል።`).catch(e=>console.warn('withdrawal pending notification failed:',e.message));
        res.json({status:'success',message:'Withdrawal request sent to admin.',requestId:ref.id});
    } catch(e){
        let msg = 'Could not submit withdrawal.';
        if (e.message === 'INSUFFICIENT_BALANCE') msg = 'Insufficient Main Balance.';
        else if (e.message === 'DEPOSIT_REQUIRED') msg = 'ገንዘብ ለማውጣት መጀመሪያ ቢያንስ አንድ ጊዜ Deposit ማድረግ አለብዎት[span_0](start_span)[span_0](end_span)[span_1](start_span)[span_1](end_span)።';
        else if (e.message === 'WIN_AFTER_DEPOSIT_REQUIRED') msg = 'ገንዘብ ለማውጣት ዲፖዚት ካደረጉ በኋላ ቢያንስ 1 ጌም ማሸነፍ አለብዎት።';
        res.status(400).json({status:'error',message:msg});
    }
});


function requireAdmin(req, res, next) {
    if (!req.telegramUserId || !ADMIN_IDS.has(req.telegramUserId)) return res.status(403).json({ status: 'error', message: 'Admin access only.' });
    next();
}
app.use('/api/admin', requireAdmin);

app.get('/api/admin/bot-settings', async (req, res) => {
    try {
        const doc = await db.collection('settings').doc('bot_settings').get();
        res.json({ status: 'success', settings: doc.exists ? doc.data() : { botCount: 50, botWinPercent: 20, botCardsPerUser: 2, restrictDepositedWin: true } });
    } catch(e) {
        res.status(500).json({ status: 'error', message: 'Could not load bot settings.' });
    }
});

app.post('/api/admin/bot-settings', async (req, res) => {
    try {
        const botCount = Number(req.body?.botCount ?? 50);
        const botWinPercent = Number(req.body?.botWinPercent ?? 20);
        const botCardsPerUser = Number(req.body?.botCardsPerUser ?? 2);
        const restrictDepositedWin = Boolean(req.body?.restrictDepositedWin);
        
        const settingsData = {
            botCount,
            botWinPercent,
            botCardsPerUser,
            restrictDepositedWin,
            updated_at: Date.now()
        };

        await db.collection('settings').doc('bot_settings').set(settingsData);
        engine.setBotSettings(settingsData);
        res.json({ status: 'success' });
    } catch(e) {
        res.status(500).json({ status: 'error', message: 'Could not save bot settings.' });
    }
});

app.get('/api/admin/promos', async (req, res) => {
    try {
        const [autoDoc, promoSnap] = await Promise.all([
            db.collection('settings').doc('auto_bonus').get(),
            db.collection('promo_codes').get()
        ]);
        const autoBonus = autoDoc.exists ? autoDoc.data() : { enabled: false, type: 'percent', value: 10, minDeposit: 100 };
        const promos = promoSnap.docs.map(doc => ({ code: doc.id, ...doc.data() }));
        res.json({ status: 'success', autoBonus, promos });
    } catch(e) {
        res.status(500).json({ status: 'error', message: 'Could not load promo settings.' });
    }
});

app.post('/api/admin/autobonus', async (req, res) => {
    try {
        const { enabled, type, value, minDeposit } = req.body || {};
        await db.collection('settings').doc('auto_bonus').set({
            enabled: Boolean(enabled),
            type: type === 'fixed' ? 'fixed' : 'percent',
            value: Number(value) || 0,
            minDeposit: Number(minDeposit) || 0,
            updated_at: Date.now()
        });
        res.json({ status: 'success' });
    } catch(e) {
        res.status(500).json({ status: 'error', message: 'Could not save auto bonus.' });
    }
});

app.post('/api/admin/promos/create', async (req, res) => {
    try {
        const code = String(req.body?.code || '').trim().toUpperCase();
        const type = req.body?.type === 'fixed' ? 'fixed' : 'percent';
        const value = Number(req.body?.value || 0);
        const minDeposit = Number(req.body?.minDeposit || 0);
        const maxUses = Number(req.body?.maxUses || 100);

        if (!code || value <= 0) return res.status(400).json({ status: 'error', message: 'Invalid code or value.' });

        await db.collection('promo_codes').doc(code).set({
            type,
            value,
            minDeposit,
            maxUses,
            usedCount: 0,
            usedBy: [],
            created_at: Date.now()
        });
        res.json({ status: 'success' });
    } catch(e) {
        res.status(500).json({ status: 'error', message: 'Could not create promo code.' });
    }
});

app.post('/api/admin/promos/delete', async (req, res) => {
    try {
        const code = String(req.body?.code || '').trim().toUpperCase();
        await db.collection('promo_codes').doc(code).delete();
        res.json({ status: 'success' });
    } catch(e) {
        res.status(500).json({ status: 'error', message: 'Could not delete promo code.' });
    }
});

app.post('/api/promo/redeem', async (req, res) => {
    const code = String(req.body?.code || '').trim().toUpperCase();
    const userId = String(req.telegramUserId);

    if (!code) return res.status(400).json({ status: 'error', message: 'እባክዎ ኮድ ያስገቡ' });

    try {
        let bonusAdded = 0;
        await db.runTransaction(async tx => {
            const promoRef = db.collection('promo_codes').doc(code);
            const userRef = db.collection('users').doc(userId);

            const [promoSnap, userSnap] = await Promise.all([tx.get(promoRef), tx.get(userRef)]);
            if (!promoSnap.exists) throw new Error('ይህ ፕሮሞ ኮድ የለም ወይም ተሰርዟል');

            const promo = promoSnap.data();
            const user = userSnap.exists ? userSnap.data() : {};

            if (promo.usedBy && promo.usedBy.includes(userId)) throw new Error('ይህንን ፕሮሞ ኮድ ከዚህ በፊት ተጠቅመዋል!');
            if (promo.usedCount >= promo.maxUses) throw new Error('የዚህ ፕሮሞ ኮድ የአጠቃቀም ገደብ አልቋል!');

            const totalDeposited = Number(user.total_deposited || 0);
            if (promo.minDeposit > 0 && totalDeposited < promo.minDeposit) {
                throw new Error(`ይህ ኮድ የሚሰራው ቢያንስ ${promo.minDeposit} ETB ዲፖዚት ላደረጉ ተጫዋቾች ብቻ ነው!`);
            }

            if (promo.type === 'percent') {
                let base = totalDeposited > 0 ? totalDeposited : 100;
                bonusAdded = Math.round((base * promo.value / 100) * 100) / 100;
            } else {
                bonusAdded = Number(promo.value || 0);
            }

            const currentBonus = Number(user.bonus || 0);
            const txs = Array.isArray(user.transactions) ? user.transactions : [];

            tx.update(userRef, {
                bonus: currentBonus + bonusAdded,
                transactions: [...txs, { type: 'promo_bonus', wallet: 'bonus', amount: bonusAdded, code, timestamp: new Date().toISOString() }]
            });

            tx.update(promoRef, {
                usedCount: (promo.usedCount || 0) + 1,
                usedBy: [...(promo.usedBy || []), userId]
            });
        });

        res.json({ status: 'success', message: 'ፕሮሞ ኮድ ተቀባይነት አግኝቷል!', bonusAdded });
    } catch (e) {
        res.status(400).json({ status: 'error', message: e.message || 'ፕሮሞ ኮድ መጠቀም አልተቻለም' });
    }
});

app.get('/api/admin/overview', async (req, res) => {
    try {
        const [users, deposits, withdrawals, rounds] = await Promise.all(['users','deposit_requests','withdrawal_requests','rounds'].map(c => db.collection(c).get()));
        const userRows = users.docs.map(d => d.data());
        const depositRows = deposits.docs.map(d => d.data());
        const withdrawalRows = withdrawals.docs.map(d => d.data());
        const pendingDeposits = depositRows.filter(d => d.status === 'pending');
        const pendingWithdrawals = withdrawalRows.filter(d => d.status === 'pending');
        const weekStart = Date.now() - 7 * 24 * 60 * 60 * 1000;
        let weeklyDeposits = 0, weeklyWithdrawals = 0, weeklyWinnings = 0;
        for (const u of userRows) for (const t of (Array.isArray(u.transactions) ? u.transactions : [])) {
            const ts = typeof t.timestamp === 'number' ? t.timestamp : Date.parse(t.timestamp || '');
            if (!Number.isFinite(ts) || ts < weekStart) continue;
            if (t.type === 'deposit') weeklyDeposits += Number(t.amount || 0);
            if (t.type === 'withdrawal_pending') weeklyWithdrawals += Number(t.amount || 0);
            if (t.type === 'win' || t.type === 'winnings') weeklyWinnings += Number(t.amount || 0);
        }
        res.json({status:'success', stats:{users:users.size, mainBalance:userRows.reduce((n,u)=>n+Number(u.balance||0),0), bonusBalance:userRows.reduce((n,u)=>n+Number(u.bonus||0),0), pendingDeposits:pendingDeposits.length, pendingWithdrawals:pendingWithdrawals.length, rounds:rounds.size, weeklyDeposits, weeklyWithdrawals, weeklyWinnings}});
    } catch(e) { console.error('admin overview',e); res.status(500).json({status:'error',message:'Could not load dashboard.'}); }
});

app.get('/api/admin/users', async (req,res)=>{
    try { const q=String(req.query.q||'').toLowerCase().slice(0,80); const snap=await db.collection('users').get(); const users=snap.docs.map(d=>({id:d.id,...d.data()})).filter(u=>!q||[u.id,u.username,u.first_name,u.phone_number].some(v=>String(v||'').toLowerCase().includes(q))).slice(0,150); res.json({status:'success',users}); }
    catch(e){res.status(500).json({status:'error',message:'Could not load users.'});}
});

app.get('/api/admin/requests', async(req,res)=>{
    try { const [d,w]=await Promise.all([db.collection('deposit_requests').get(),db.collection('withdrawal_requests').get()]); const map=(snap,type)=>snap.docs.map(x=>({id:x.id,type,...x.data()})); res.json({status:'success',requests:[...map(d,'deposit'),...map(w,'withdrawal')].sort((a,b)=>Number(b.created_at||0)-Number(a.created_at||0)).slice(0,250)}); }
    catch(e){res.status(500).json({status:'error',message:'Could not load requests.'});}
});

app.post('/api/admin/review', async(req,res)=>{
    const {id,type,approve}=req.body||{}; if(!id||!['deposit','withdrawal'].includes(type)||typeof approve!=='boolean') return res.status(400).json({status:'error',message:'Invalid review.'});
    const reqRef=db.collection(type==='deposit'?'deposit_requests':'withdrawal_requests').doc(String(id));
    try {
        let userId='';
        await db.runTransaction(async tx=>{
            const rs=await tx.get(reqRef); if(!rs.exists||rs.data().status!=='pending') throw new Error('ALREADY_PROCESSED');
            const r=rs.data(); userId=String(r.user_id); const ur=db.collection('users').doc(userId); const us=await tx.get(ur); if(!us.exists) throw new Error('USER_NOT_FOUND'); const u=us.data(); const txs=Array.isArray(u.transactions)?u.transactions:[];
            
            if(type==='deposit'&&approve) {
                let depositAmount = Number(r.amount);
                let addBonus = 0;
                
                const autoBonusSnap = await tx.get(db.collection('settings').doc('auto_bonus'));
                if (autoBonusSnap.exists) {
                    const ab = autoBonusSnap.data();
                    if (ab.enabled && depositAmount >= (ab.minDeposit || 0)) {
                        if (ab.type === 'percent') {
                            addBonus = (depositAmount * ab.value) / 100;
                        } else {
                            addBonus = Number(ab.value || 0);
                        }
                    }
                }

                const currentBonus = Number(u.bonus || 0);
                const totalDeposited = Number(u.total_deposited || 0) + depositAmount;

                tx.update(ur,{
                    bonus: currentBonus + depositAmount + addBonus,
                    total_deposited: totalDeposited,
                    has_deposited: true,
                    first_deposit_at: u.first_deposit_at || Date.now(),
                    transactions:[
                        ...txs,
                        {type:'deposit', wallet:'bonus', amount: depositAmount, status:'approved', request_id:String(id), timestamp:new Date().toISOString()},
                        ...(addBonus > 0 ? [{type:'auto_deposit_bonus', wallet:'bonus', amount: addBonus, status:'approved', timestamp:new Date().toISOString()}] : [])
                    ]
                });
            }

            if(type==='withdrawal'&&!approve) tx.update(ur,{balance:Number(u.balance||0)+Number(r.amount),transactions:[...txs,{type:'withdrawal_refund',amount:Number(r.amount),request_id:String(id),timestamp:new Date().toISOString()}]});
            tx.update(reqRef,{status:approve?'approved':'rejected',reviewed_at:Date.now(),reviewed_by:req.telegramUserId});
        });
        const reviewed = (await reqRef.get()).data() || {};
        const amountLabel = `${Number(reviewed.amount || 0).toFixed(2)} ETB`;
        const refLabel = `Request ID: ${id}`;
        const notice = type === 'deposit'
            ? `${approve ? '✅ DEPOSIT APPROVED' : '❌ DEPOSIT REJECTED'}\nAmount: ${amountLabel}\n${refLabel}\n${approve ? 'Bonus Balance ላይ ተጨምሯል።' : 'እባክዎ የክፍያ መረጃውን ያረጋግጡ ወይም Admin ያነጋግሩ።'}`
            : `${approve ? '✅ WITHDRAWAL APPROVED' : '❌ WITHDRAWAL REJECTED'}\nAmount: ${amountLabel}\n${refLabel}\n${approve ? 'ጥያቄው ተፈቅዷል፤ Admin በTelebirr ክፍያው ይልካል።' : 'ገንዘቡ ወደ Main Balance ተመልሷል።'}`;
        await bot.telegram.sendMessage(userId, notice).catch(e=>console.warn('wallet review notification failed:',e.message));
        res.json({status:'success'});
    } catch(e){res.status(e.message==='ALREADY_PROCESSED'?409:400).json({status:'error',message:e.message==='ALREADY_PROCESSED'?'Already reviewed.':'Review failed.'});}
});

app.post('/api/admin/user-action', async(req,res)=>{
    const {userId,action,amount,walletType='main'}=req.body||{};
    if(!userId||!['block','unblock','credit','debit'].includes(action)||!['main','bonus'].includes(walletType)) return res.status(400).json({status:'error',message:'Invalid action.'});
    try {
        const ref=db.collection('users').doc(String(userId)); let result;
        await db.runTransaction(async tx=>{
            const snap=await tx.get(ref); if(!snap.exists)throw new Error('USER_NOT_FOUND'); const u=snap.data(); const changes={};
            if(action==='block')changes.blocked=true; if(action==='unblock')changes.blocked=false;
            if(action==='credit'||action==='debit'){
                const n=Number(amount); if(!Number.isFinite(n)||n<=0||n>1000000)throw new Error('INVALID_AMOUNT');
                const field=walletType==='bonus'?'bonus':'balance'; const current=Number(u[field]||0); const next=current+(action==='credit'?n:-n);
                if(next<0)throw new Error('INSUFFICIENT_BALANCE'); changes[field]=next;
                changes.transactions=[...(Array.isArray(u.transactions)?u.transactions:[]),{type:`admin_${action}_${walletType}`,wallet:walletType,amount:n,admin_id:req.telegramUserId,timestamp:new Date().toISOString()}];
            }
            tx.update(ref,changes); result=changes;
        });
        await db.collection('admin_audit').doc().set({admin_id:req.telegramUserId,user_id:String(userId),action,wallet:walletType,amount:Number(amount)||0,at:Date.now()});
        res.json({status:'success',result});
    } catch(e){res.status(400).json({status:'error',message:e.message==='USER_NOT_FOUND'?'User not found.':e.message==='INSUFFICIENT_BALANCE'?'Insufficient balance.':'Action failed.'});}
});

app.post('/api/admin/broadcast', async(req,res)=>{
    const message=String(req.body?.message||'').trim();
    const audience=String(req.body?.audience||'all');
    const buttonText=String(req.body?.buttonText||'').trim().slice(0,64);
    const buttonUrl=String(req.body?.buttonUrl||'').trim();
    const imageData=String(req.body?.imageBase64||'');
    if(!['all','verified','unverified'].includes(audience)) return res.status(400).json({status:'error',message:'Invalid audience.'});
    if(!message && !imageData) return res.status(400).json({status:'error',message:'Add text or an image.'});
    if(message.length>1000) return res.status(400).json({status:'error',message:'Caption/text is too long (maximum 1000 characters).'});
    if(buttonUrl){try{const u=new URL(buttonUrl);if(!['https:','http:'].includes(u.protocol))throw new Error();}catch(_){return res.status(400).json({status:'error',message:'Button URL must be a valid http/https link.'});}}
    if(buttonText && !buttonUrl) return res.status(400).json({status:'error',message:'Enter a URL for the button.'});
    let photoBuffer=null;
    if(imageData){
        const m=imageData.match(/^data:image\/(jpeg|jpg|png|webp);base64,([A-Za-z0-9+/=]+)$/i);
        if(!m) return res.status(400).json({status:'error',message:'Use JPG, PNG or WEBP image.'});
        photoBuffer=Buffer.from(m[2],'base64');
        if(photoBuffer.length>7*1024*1024) return res.status(400).json({status:'error',message:'Image must be 7 MB or smaller.'});
    }
    try {
        const snap=await db.collection('users').get();
        const ids=snap.docs.filter(d=>{
            const u=d.data()||{}; if(u.blocked)return false;
            const verified=Boolean(String(u.phone_number||'').trim());
            return audience==='all'||(audience==='verified'?verified:!verified);
        }).map(d=>d.id);
        const extra=buttonText&&buttonUrl?{reply_markup:{inline_keyboard:[[{text:buttonText,url:buttonUrl}]]}}:{};
        let sent=0, failed=0;
        for(const id of ids){
            try{
                if(photoBuffer) await bot.telegram.sendPhoto(id,{source:photoBuffer,filename:'broadcast-image.'+(imageData.match(/^data:image\/(jpeg|jpg|png|webp)/i)?.[1]||'jpg')},{caption:message||undefined,...extra});
                else await bot.telegram.sendMessage(id,message,extra);
                sent++;
            }catch(e){failed++;}
                await new Promise(resolve=>setTimeout(resolve,45));
        }
        await db.collection('admin_audit').doc().set({admin_id:req.telegramUserId,action:'broadcast',audience,has_photo:Boolean(photoBuffer),has_button:Boolean(buttonUrl),sent,failed,total:ids.length,at:Date.now()});
        res.json({status:'success',total:ids.length,sent,failed});
    } catch(e){console.error('broadcast failed',e);res.status(500).json({status:'error',message:'Broadcast failed.'});}
});

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
            '🎧 እርዳታ ለማግኘት @Melbetsupporter_bot ያነጋግሩ።'
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
