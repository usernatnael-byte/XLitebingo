const { Telegraf, Markup, session } = require('telegraf');
const { admin, db } = require('./firebase');

const BOT_TOKEN = process.env.BOT_TOKEN;
if (!BOT_TOKEN) throw new Error('BOT_TOKEN environment variable is required');

const WEBAPP_URL = process.env.WEBAPP_URL || 'https://xlitebingo.onrender.com';
const CHANNEL_ID = process.env.BOT_CHANNEL_ID || '-1004418660495';
const CHANNEL_URL = process.env.BOT_CHANNEL_URL || 'https://t.me/test16746g';
const ADMIN_IDS = new Set([...(process.env.ADMIN_ID || '7396414604').split(','), ...(process.env.ADMIN_IDS || '').split(',')].map(v => v.trim()).filter(Boolean));

const REGISTRATION_BONUS = Number(process.env.REGISTRATION_BONUS_ETB || 10);
const REFERRAL_BONUS = Number(process.env.REFERRAL_BONUS_ETB || 20);

const DEPOSIT_MINIMUM = Math.max(100, Number(process.env.DEPOSIT_MINIMUM_ETB || 100));
const WITHDRAW_MINIMUM = Math.max(1, Number(process.env.WITHDRAW_MINIMUM_ETB || 100));
const DEPOSIT_INSTRUCTIONS = process.env.DEPOSIT_INSTRUCTIONS ||
    '💰 ሂሳብ ለመሙላት Telebirr ይምረጡ።\n\nአነስተኛ መጠን: 100 ETB\n👤 ስም: Esraeal\n📱 አካውንት: 0949196145\n\nብሩን ከላኩ በኋላ የክፍያ ማረጋገጫ SMS ወይም የደረሰኝ ፎቶ (Screenshot) ይላኩ። አድሚኑ ካረጋገጠው በኋላ Bonus Balance ይጨመራል።';
const ADMIN_ID_LIST = [...new Set([...ADMIN_IDS])];

const SUPPORT_CONTACT = process.env.SUPPORT_CONTACT || '@Melbetsupporter_bot';

if (!CHANNEL_ID || !CHANNEL_URL) {
    console.warn('BOT_CHANNEL_ID and BOT_CHANNEL_URL must be set to enforce mandatory channel joining.');
}

const bot = new Telegraf(BOT_TOKEN);
bot.use(session());

// 🛡️ ግሎባል ቴሌግራም ደህንነት ማስተካከያ (ብሎክ ያደረጉ ተጠቃሚዎች ሰርቨሩን እንዳይዘጉት)
bot.catch((err, ctx) => {
    console.error(`Telegram Bot Error for update ${ctx.update?.update_id || 'unknown'}:`, err?.message || err);
});

bot.use(async (ctx, next) => {
    if (!ctx.from || String(ctx.from.id) === '') return next();
    if (ADMIN_IDS.has(String(ctx.from.id))) return next();
    try {
        const snap = await db.collection('users').doc(String(ctx.from.id)).get();
        if (snap.exists && snap.data().blocked) {
            return ctx.reply('⛔ የመለያዎ መዳረሻ በአድሚን ታግዷል።').catch(() => {});
        }
    } catch (e) { console.error('Block status check failed:', e.message); }
    return next();
});

function isAdmin(ctx) {
    return ADMIN_IDS.has(String(ctx.from?.id));
}

function money(v) {
    return `${Number(v || 0).toFixed(2)} ETB`;
}

async function isChannelMember(ctx) {
    if (!CHANNEL_ID) return false;

    try {
        const m = await ctx.telegram.getChatMember(CHANNEL_ID, ctx.from.id);

        return (
            ['creator', 'administrator', 'member'].includes(m.status) ||
            (m.status === 'restricted' && m.is_member === true)
        );
    } catch (e) {
        console.error('Channel membership check failed:', e.message);
        return false;
    }
}

async function askToJoin(ctx) {
    return ctx.reply(
        '👋 ወደ MELBET BINGO እንኳን በደህና መጡ!\n\nቀጥለው ለመሄድ መጀመሪያ የTelegram ቻናላችንን ይቀላቀሉ። ከገቡ በኋላ “✅ ቻናሉን ተቀላቅያለሁ” ይጫኑ።',
        Markup.inlineKeyboard([
            [Markup.button.url('📢 ቻናሉን ተቀላቀል', CHANNEL_URL)],
            [Markup.button.callback('✅ MELBET ቻናሉን ተቀላቅያለሁ', 'verify_channel')]
        ])
    ).catch(e => console.warn('askToJoin failed:', e.message));
}

function askForContact(ctx) {
    return ctx.reply(
        '✅ MELBET ቻናሉን በትክክል ተቀላቅለዋል።\n\nምዝገባውን ለማጠናቀቅ የራስዎን ስልክ ቁጥር ያጋሩ።',
        Markup.keyboard([
            [Markup.button.contactRequest('📱 ስልክ ቁጥሮን አጋራ')]
        ]).resize().oneTime()
    ).catch(e => console.warn('askForContact failed:', e.message));
}

async function showMainMenu(ctx) {
    const replyMarkup = {
        inline_keyboard: [
            [
                { text: "🎮 Play Melbet Bingo", web_app: { url: WEBAPP_URL }, style: "primary" }
            ],
            [
                { text: "💵 Balance", callback_data: "account", style: "success" },
                { text: "🔗 Invite", callback_data: "refer", style: "danger" }
            ],
            [
                { text: "🎮 Game Rules", callback_data: "rules", style: "primary" },
                { text: "🆘 Support", callback_data: "support", style: "primary" }
            ]
        ]
    };

    if (isAdmin(ctx)) {
        replyMarkup.inline_keyboard.push([
            { text: "🛠 Admin Panel", web_app: { url: `${WEBAPP_URL}/admin` }, style: "primary" }
        ]);
    }

    await ctx.reply(
        'MelBet ከታች ካሉት አማራጮች ይምረጡ።',
        { reply_markup: replyMarkup }
    ).catch(e => console.warn('showMainMenu failed:', e.message));
}

// ==================== ADMIN APPROVE & REJECT COMMANDS ====================

bot.command('approve', async (ctx) => {
    if (!isAdmin(ctx)) return;
    const args = ctx.message.text.split(' ');
    const reqId = args[1];
    if (!reqId) return ctx.reply('⚠️ እባክዎ ጥያቄ ቁጥር (Request ID) ያስገቡ።\nምሳሌ: /approve 4503');

    try {
        let qSnap = await db.collection('deposit_requests').where('req_id', '==', reqId).get();

        if (!qSnap.empty) {
            const docSnap = qSnap.docs[0];
            const docRef = docSnap.ref;
            const data = docSnap.data();
            if (data.status === 'approved') return ctx.reply('⚠️ ይህ ጥያቄ ቀድሞ ጸድቋል።');

            const userId = data.user_id;
            const amount = Number(data.amount || 0);
            const userRef = db.collection('users').doc(userId);

            await db.runTransaction(async (tx) => {
                const userSnap = await tx.get(userRef);
                if (!userSnap.exists) throw new Error('USER_NOT_FOUND');
                const uData = userSnap.data();

                const currentBalance = Number(uData.balance || 0);
                const newBalance = currentBalance + amount;

                tx.update(userRef, {
                    balance: newBalance,
                    has_deposited: true,
                    transactions: [
                        ...(uData.transactions || []),
                        {
                            type: 'deposit',
                            amount: amount,
                            timestamp: new Date().toISOString()
                        }
                    ]
                });

                tx.update(docRef, { status: 'approved' });
            });

            await ctx.reply(`✅ የዲፖዚት ጥያቄ #${reqId} ተጸድቆ ${amount} ብር ለተጠቃሚው ተጭኗል!`);
            await bot.telegram.sendMessage(userId, `🎉 የ ${amount} ብር የዲፖዚት ጥያቄዎ በአድሚን ጸድቋል! አካውንትዎ ላይ ተጭኗል።`).catch(() => {});
            return;
        }

        let wSnap = await db.collection('withdrawal_requests').where('req_id', '==', reqId).get();

        if (!wSnap.empty) {
            const docSnap = wSnap.docs[0];
            const wRef = docSnap.ref;
            const wData = docSnap.data();
            if (wData.status === 'approved') return ctx.reply('⚠️ ይህ የዊዝድሮው ጥያቄ ቀድሞ ጸድቋል።');

            await wRef.update({ status: 'approved' });
            await ctx.reply(`✅ የዊዝድሮው ጥያቄ #${reqId} ጸድቋል!`);
            await bot.telegram.sendMessage(wData.user_id, `🎉 የ ${wData.amount} ብር የገንዘብ ማውጣት (Withdrawal) ጥያቄዎ ጸድቆ ተልኳል!`).catch(() => {});
            return;
        }

        return ctx.reply(`❌ ጥያቄ ቁጥር #${reqId} አልተገኘም!`);

    } catch (e) {
        console.error('Approve command error:', e);
        ctx.reply('⚠️ ስህተት ተፈጥሯል: ' + e.message);
    }
});

bot.command('reject', async (ctx) => {
    if (!isAdmin(ctx)) return;
    const textParts = ctx.message.text.split(' ');
    const reqId = textParts[1];
    const reason = textParts.slice(2).join(' ') || 'ምንም ምክንያት አልተሰጠም';

    if (!reqId) return ctx.reply('⚠️ እባክዎ ጥያቄ ቁጥር እና ምክንያት ያስገቡ።\nምሳሌ: /reject 4503 የተሳሳተ ትራንዛክሽን');

    try {
        let qSnap = await db.collection('deposit_requests').where('req_id', '==', reqId).get();

        if (!qSnap.empty) {
            const docSnap = qSnap.docs[0];
            const data = docSnap.data();
            await docSnap.ref.update({ status: 'rejected', reject_reason: reason });
            await ctx.reply(`❌ የዲፖዚት ጥያቄ #${reqId} ተሰርዟል።`);
            await bot.telegram.sendMessage(data.user_id, `❌ የዲፖዚት ጥያቄዎ ውድቅ ተደርጓል።\nምክንያት: ${reason}`).catch(() => {});
            return;
        }

        let wSnap = await db.collection('withdrawal_requests').where('req_id', '==', reqId).get();

        if (!wSnap.empty) {
            const docSnap = wSnap.docs[0];
            const wData = docSnap.data();
            const userId = wData.user_id;
            const amount = Number(wData.amount || 0);
            const userRef = db.collection('users').doc(userId);

            await db.runTransaction(async (tx) => {
                const userSnap = await tx.get(userRef);
                if (userSnap.exists) {
                    const uData = userSnap.data();
                    tx.update(userRef, {
                        balance: Number(uData.balance || 0) + amount
                    });
                }
                tx.update(docSnap.ref, { status: 'rejected', reject_reason: reason });
            });

            await ctx.reply(`❌ የዊዝድሮው ጥያቄ #${reqId} ተሰርዟል (ገንዘቡ ተመላሽ ሆኗል)።`);
            await bot.telegram.sendMessage(userId, `❌ የገንዘብ ማውጣት ጥያቄዎ ውድቅ ተደርጓል (ገንዘቡ ወደ አካውንትዎ ተመልሷል)።\nምክንያት: ${reason}`).catch(() => {});
            return;
        }

        return ctx.reply(`❌ ጥያቄ ቁጥር #${reqId} አልተገኘም!`);

    } catch (e) {
        console.error('Reject command error:', e);
        ctx.reply('⚠️ ስህተት ተፈጥሯል: ' + e.message);
    }
});

bot.on('callback_query', async (ctx) => {
    const action = ctx.callbackQuery?.data;
    const chatId = ctx.callbackQuery?.message?.chat?.id;
    const userId = String(ctx.from.id);

    if (!action || !chatId) return;

    if (action.startsWith('dp_') || action.startsWith('wd_')) {
        return;
    }

    if (action !== 'verify_channel') {
        await ctx.answerCbQuery().catch(() => {});
    }

    if (action === 'verify_channel') {
        await ctx.answerCbQuery().catch(() => {});

        const isMember = await isChannelMember(ctx);
        if (!isMember) {
            return ctx.reply('❌ እስካሁን ቻናሉን አልተቀላቀሉም። እባክዎ መጀመሪያ ቻናሉን ይቀላቀሉ።', 
                Markup.inlineKeyboard([
                    [Markup.button.url('📢 ቻናሉን ተቀላቀል', CHANNEL_URL)],
                    [Markup.button.callback('✅ MELBET ቻናሉን ተቀላቅያለሁ', 'verify_channel')]
                ])
            ).catch(() => {});
        }

        await db.collection('users').doc(userId).set({
            channel_joined: true
        }, { merge: true });

        const doc = await db.collection('users').doc(userId).get();
        if (!doc.exists || !doc.data().phone_number) {
            return askForContact(ctx);
        }

        return showMainMenu(ctx);
    }

    if (action === 'account') {
        const snap = await db.collection('users').doc(userId).get();

        if (!snap.exists) {
            return ctx.telegram.sendMessage(
                chatId,
                'መጀመሪያ /start በመላክ ይመዝገቡ።'
            ).catch(() => {});
        }

        const d = snap.data();

        return ctx.telegram.sendMessage(
            chatId,
            `👤 የእርስዎ ሂሳብ\n` +
            `💵 Main Balance: ${money(d.balance)}\n` +
            `🎁 Bonus Balance: ${money(d.bonus)}\n` +
            `💳 Deposit አድርገዋል: ${d.has_deposited ? 'አዎ' : 'ገና አይደለም'}`
        ).catch(() => {});
    }

    if (action === 'refer') {
        const me = await ctx.telegram.getMe();
        const link = `https://t.me/${me.username}?start=ref_${userId}`;

        return ctx.telegram.sendMessage(
            chatId,
            `🎁 ጓደኛዎን ይጋብዙ። በሊንክዎ ተመዝግቦ ስልኩን ሲያረጋግጥ 20 ETB Bonus ያገኛሉ።\n\n${link}`,
            Markup.inlineKeyboard([
                [Markup.button.url(
                    '📨 ሊንኩን አጋራ',
                    `https://t.me/share/url?url=${encodeURIComponent(link)}`
                )]
            ])
        ).catch(() => {});
    }

    if (action === 'rules') {
        return ctx.telegram.sendMessage(
            chatId,
            '🎮 የBingo ህጎች\n' +
            '• አንድ ካርድ 10 ETB ነው።\n' +
            '• Bonus Balance ቀድሞ ይቀነሳል፤ ቀሪው ከMain Balance ይቀነሳል።\n' +
            '• የጨዋታ ሽልማት ወደ Main Balance ይገባል።\n' +
            '• ገንዘብ ለማውጣት ቢያንስ አንድ ጊዜ Deposit ማድረግ ያስፈልጋል።'
        ).catch(() => {});
    }

    if (action === 'support') {
        return ctx.telegram.sendMessage(
            chatId,
            `🎧 እርዳታ ለማግኘት ${SUPPORT_CONTACT} ያነጋግሩ።`
        ).catch(() => {});
    }
});

async function completeRegistration(ctx, phoneNumber) {
    const uid = String(ctx.from.id);

    const userRef = db.collection('users').doc(uid);
    const pendingRef = db.collection('pending_registrations').doc(uid);

    await db.runTransaction(async tx => {
        const userSnap = await tx.get(userRef);
        const pendingSnap = await tx.get(pendingRef);

        if (userSnap.exists) {
            tx.set(userRef, {
                phone_number: phoneNumber,
                channel_joined: true
            }, { merge: true });

            return;
        }

        const pending = pendingSnap.exists ? pendingSnap.data() : {};

        const referrerId =
            pending.referrer_id && String(pending.referrer_id) !== uid
                ? String(pending.referrer_id)
                : null;

        const referrerRef = referrerId
            ? db.collection('users').doc(referrerId)
            : null;

        const referrerSnap = referrerRef
            ? await tx.get(referrerRef)
            : null;

        const now = new Date().toISOString();

        tx.set(userRef, {
            telegram_id: uid,
            first_name: ctx.from.first_name || '',
            username: ctx.from.username || '',
            phone_number: phoneNumber,
            balance: 0,
            bonus: REGISTRATION_BONUS,
            channel_joined: true,
            has_deposited: false,
            referral_code: uid,
            referred_by: referrerSnap?.exists ? referrerId : null,
            created_at: Date.now(),
            transactions: [{
                type: 'bonus',
                amount: REGISTRATION_BONUS,
                source: 'registration',
                timestamp: now
            }]
        });

        if (referrerSnap?.exists) {
            const rd = referrerSnap.data();

            const referred = Array.isArray(rd.referred_users)
                ? rd.referred_users
                : [];

            if (!referred.includes(uid)) {
                const txs = Array.isArray(rd.transactions)
                    ? rd.transactions
                    : [];

                txs.push({
                    type: 'bonus',
                    amount: REFERRAL_BONUS,
                    source: 'referral',
                    referred_user: uid,
                    timestamp: now
                });

                tx.update(referrerRef, {
                    bonus: Number(rd.bonus || 0) + REFERRAL_BONUS,
                    referred_users: [...referred, uid],
                    referral_count: Number(rd.referral_count || 0) + 1,
                    transactions: txs
                });
            }
        }

        tx.delete(pendingRef);
    });
}

bot.start(async ctx => {
    try {
        const uid = String(ctx.from.id);
        const payload = String(ctx.startPayload || '').toLowerCase();

        if (payload.startsWith('ref_')) {
            const referrerId = payload.slice(4).replace(/[^0-9]/g, '');

            if (referrerId && referrerId !== uid) {
                const existing = await db.collection('users').doc(uid).get();

                if (!existing.exists) {
                    await db.collection('pending_registrations')
                        .doc(uid)
                        .set({ referrer_id: referrerId }, { merge: true });
                }
            }
        }

        const userDoc = await db.collection('users').doc(uid).get();

        if (!await isChannelMember(ctx)) {
            return askToJoin(ctx);
        }

        if (!userDoc.exists || !userDoc.data().phone_number) {
            return askForContact(ctx);
        }

        await db.collection('users').doc(uid).set({
            channel_joined: true
        }, { merge: true });

        await showMainMenu(ctx);

    } catch (e) {
        console.error('/start error:', e);
        ctx.reply('⚠️ ጊዜያዊ ችግር ተፈጥሯል። እባክዎ /start እንደገና ይላኩ።').catch(() => {});
    }
});

bot.on('contact', async ctx => {
    try {
        const contact = ctx.message.contact;

        if (String(contact.user_id) !== String(ctx.from.id)) {
            return ctx.reply('⚠️ እባክዎ የራስዎን ስልክ ቁጥር ብቻ ያጋሩ።').catch(() => {});
        }

        if (!await isChannelMember(ctx)) {
            return askToJoin(ctx);
        }

        let phone = String(contact.phone_number || '');

        if (!phone.startsWith('+')) {
            phone = `+${phone}`;
        }

        await completeRegistration(ctx, phone);
        await showMainMenu(ctx);

    } catch (e) {
        console.error('Contact registration error:', e);
        ctx.reply('⚠️ ምዝገባው አልተሳካም። እባክዎ እንደገና ይሞክሩ።').catch(() => {});
    }
});

bot.command('cancel', ctx => {
    if (!ctx.session) ctx.session = {};
    ctx.session.flow = null;
    ctx.session.depositAmount = null;
    ctx.session.withdrawAmount = null;
    ctx.session.withdrawName = null;
    ctx.session.withdrawAccount = null;

    ctx.reply('ተሰርዟል።').catch(() => {});
});

bot.on('text', async ctx => {
    if (!ctx.session) ctx.session = {};
    const flow = ctx.session?.flow;

    if (!flow || ctx.message.text.startsWith('/')) return;

    const amount = Number(ctx.message.text.replace(',', '.'));

    if (flow === 'deposit_proof') {
        const amountProof = Number(ctx.session.depositAmount || 0);

        if (!amountProof) {
            ctx.session.flow = null;
            return ctx.reply('Deposit እንደገና ይጀምሩ።').catch(() => {});
        }

        const proofRef = db.collection('deposit_requests').doc();
        const shortReqId = Math.floor(1000 + Math.random() * 9000).toString();

        await proofRef.set({
            req_id: shortReqId,
            user_id: String(ctx.from.id),
            amount: amountProof,
            receipt_text: ctx.message.text.slice(0, 1500),
            status: 'pending',
            created_at: Date.now()
        });

        ctx.session.flow = null;
        ctx.session.depositAmount = null;

        await ctx.reply('✅ የክፍያ SMS/Transaction መረጃዎ ተልኳል። አድሚኑ ካረጋገጠው በኋላ Main Balance ይጨመራል።').catch(() => {});

        const adminMsgText = 
            `🔔 አዲስ ገቢ ጥያቄ #${shortReqId} (Mini App)\n` +
            `ተጠቃሚ: ${ctx.from.first_name || 'User'} (${ctx.from.username ? '@' + ctx.from.username : 'id:' + ctx.from.id}, id:${ctx.from.id})\n` +
            `መንገድ: telebirr\n` +
            `መጠን: ${amountProof} ብር\n` +
            `ዝርዝር: ${ctx.message.text.slice(0, 500)}\n\n` +
            `ለማጽደቅ: /approve ${shortReqId}\n` +
            `ለመሰረዝ: /reject ${shortReqId} <ምክንያት>`;

        for (const aid of ADMIN_ID_LIST) {
            await bot.telegram.sendMessage(aid, adminMsgText).catch(() => {});
        }

        return;
    }

    if (flow === 'withdraw_details') {
        const parts = ctx.message.text.trim().split(/\s*\|\s*/);

        if (parts.length < 2 || parts[0].length < 2 || parts[1].length < 5) {
            return ctx.reply('እባክዎ በዚህ ቅርጽ ይላኩ፦ ስም | Telebirr ቁጥር\nምሳሌ: Natnael | 09XXXXXXXX').catch(() => {});
        }

        ctx.session.withdrawName = parts[0].slice(0, 80);
        ctx.session.withdrawAccount = parts[1].slice(0, 40);
        ctx.session.flow = 'withdraw_confirm';

        return ctx.reply(`እባክዎ የWithdrawal መረጃዎን ያረጋግጡ፦\nስም: ${ctx.session.withdrawName}\nTelebirr: ${ctx.session.withdrawAccount}\n\nለመቀጠል CONFIRM ይጻፉ፣ ለመሰረዝ /cancel ይጻፉ።`).catch(() => {});
    }

    if (flow === 'withdraw_confirm') {
        if (ctx.message.text.trim().toUpperCase() !== 'CONFIRM') {
            return ctx.reply('ለማረጋገጥ CONFIRM ይጻፉ ወይም /cancel ይጠቀሙ።').catch(() => {});
        }

        const uid = String(ctx.from.id);
        const amount2 = Number(ctx.session.withdrawAmount || 0);
        const userRef = db.collection('users').doc(uid);
        const requestRef = db.collection('withdrawal_requests').doc();
        const shortReqId = Math.floor(1000 + Math.random() * 9000).toString();

        try {
            await db.runTransaction(async tx => {
                const us = await tx.get(userRef);

                if (!us.exists) throw new Error('USER_NOT_FOUND');

                const d = us.data();

                if (!d.has_deposited) throw new Error('DEPOSIT_REQUIRED');

                if (Number(d.balance || 0) < amount2) {
                    throw new Error('INSUFFICIENT_BALANCE');
                }

                tx.update(userRef, {
                    balance: Number(d.balance || 0) - amount2,
                    transactions: [
                        ...(d.transactions || []),
                        {
                            type: 'withdrawal_pending',
                            amount: amount2,
                            request_id: requestRef.id,
                            timestamp: new Date().toISOString()
                        }
                    ]
                });

                tx.set(requestRef, {
                    req_id: shortReqId,
                    user_id: uid,
                    player_name: d.first_name || ctx.from.first_name || '',
                    username: d.username || ctx.from.username || '',
                    phone_number: d.phone_number || '',
                    payout_name: ctx.session.withdrawName,
                    payout_account: ctx.session.withdrawAccount,
                    payment_method: 'Telebirr',
                    amount: amount2,
                    status: 'pending',
                    created_at: Date.now()
                });
            });

            ctx.session.flow = null;
            ctx.session.withdrawAmount = null;

            await ctx.reply('✅ የWithdrawal ጥያቄዎ ወደ Admin Panel ተልኳል። አድሚኑ ካጸደቀ በኋላ ክፍያውን በTelebirr ይልካል።').catch(() => {});

            const adminMsgText = 
                `🔔 አዲስ የገንዘብ ማውጣት (Withdraw) ጥያቄ #${shortReqId}\n` +
                `ተጠቃሚ: ${ctx.from.first_name || 'User'} (${ctx.from.username ? '@' + ctx.from.username : 'id:' + uid}, id:${uid})\n` +
                `መጠን: ${amount2} ብር\n` +
                `ስም: ${ctx.session.withdrawName}\n` +
                `አካውንት: ${ctx.session.withdrawAccount}\n\n` +
                `ለማጽደቅ: /approve ${shortReqId}\n` +
                `ለመሰረዝ: /reject ${shortReqId} <ምክንያት>`;

            for (const aid of ADMIN_ID_LIST) {
                await bot.telegram.sendMessage(aid, adminMsgText).catch(() => {});
            }

        } catch (e) {
            ctx.session.flow = null;
            ctx.session.withdrawAmount = null;

            return ctx.reply(
                e.message === 'INSUFFICIENT_BALANCE'
                    ? '❌ Main Balance በቂ አይደለም።'
                    : '⚠️ Withdrawal አልተሳካም።'
            ).catch(() => {});
        }

        return;
    }

    if (flow === 'deposit_amount' || flow === 'withdraw_amount') {
        if (!Number.isFinite(amount) || amount <= 0 || amount > 1000000) {
            return ctx.reply('እባክዎ ትክክለኛ የETB መጠን ያስገቡ።').catch(() => {});
        }
    }

    if (flow === 'deposit_amount') {
        if (amount < DEPOSIT_MINIMUM) {
            return ctx.reply(`❌ አነስተኛ Deposit ${DEPOSIT_MINIMUM} ETB ነው። እባክዎ እንደገና ያስገቡ።`).catch(() => {});
        }

        ctx.session.flow = null;
        ctx.session.depositAmount = Math.round(amount * 100) / 100;
        ctx.session.flow = 'deposit_proof';

        return ctx.reply(
            `የDeposit መጠን ${money(amount)} ተቀብለናል። እባክዎ የክፍያ SMS ጽሑፍ ወይም የደረሰኝ ፎቶ (Screenshot) ይላኩ።`
        ).catch(() => {});
    }

    if (flow === 'withdraw_amount') {
        if (amount < WITHDRAW_MINIMUM) {
            return ctx.reply(`❌ ዝቅተኛ Withdrawal ${WITHDRAW_MINIMUM} ETB ነው።`).catch(() => {});
        }

        const amount2 = Math.round(amount * 100) / 100;
        const snap = await db.collection('users').doc(String(ctx.from.id)).get();

        if (!snap.exists || Number(snap.data().balance || 0) < amount2) {
            return ctx.reply('❌ Main Balance በቂ አይደለም።').catch(() => {});
        }

        ctx.session.withdrawAmount = amount2;
        ctx.session.flow = 'withdraw_details';

        return ctx.reply('የTelebirr ተቀባይ ስምዎን እና ቁጥርዎን በዚህ ቅርጽ ይላኩ፦\nስም | 09XXXXXXXX').catch(() => {});
    }
});

bot.on('photo', async ctx => {
    if (!ctx.session) ctx.session = {};
    if (ctx.session?.flow !== 'deposit_proof') return;

    const amount = Number(ctx.session.depositAmount || 0);

    if (!amount) {
        ctx.session.flow = null;
        return ctx.reply('እባክዎ Deposit እንደገና ይጀምሩ።').catch(() => {});
    }

    const ref = db.collection('deposit_requests').doc();
    const shortReqId = Math.floor(1000 + Math.random() * 9000).toString();

    await ref.set({
        req_id: shortReqId,
        user_id: String(ctx.from.id),
        amount,
        photo_file_id: ctx.message.photo.at(-1).file_id,
        status: 'pending',
        created_at: Date.now()
    });

    ctx.session.flow = null;
    ctx.session.depositAmount = null;

    await ctx.reply(
        '✅ የDeposit ማረጋገጫዎ ተልኳል። አድሚኑ ካረጋገጠው በኋላ Main Balance ይጨመራል።'
    ).catch(() => {});

    const adminMsgText = 
        `🔔 አዲስ ገቢ ጥያቄ #${shortReqId} (ፎቶ - Mini App)\n` +
        `ተጠቃሚ: ${ctx.from.first_name || 'User'} (${ctx.from.username ? '@' + ctx.from.username : 'id:' + ctx.from.id}, id:${ctx.from.id})\n` +
        `መንገድ: telebirr\n` +
        `መጠን: ${amount} ብር\n\n` +
        `ለማጽደቅ: /approve ${shortReqId}\n` +
        `ለመሰረዝ: /reject ${shortReqId} <ምክንያት>`;

    for (const aid of ADMIN_ID_LIST) {
        await bot.telegram.sendPhoto(
            aid,
            ctx.message.photo.at(-1).file_id,
            { caption: adminMsgText }
        ).catch(() => {});
    }
});

bot.launch().then(() => {
    console.log('Telegram bot is running...');
}).catch(err => {
    console.error('Failed to launch bot:', err);
});

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));

module.exports = bot;
