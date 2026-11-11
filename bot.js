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
const ADMIN_ID = (process.env.ADMIN_ID || '7396414604').split(',')[0].trim();
const ADMIN_ID_LIST = [...new Set([...ADMIN_IDS])];

const SUPPORT_CONTACT = process.env.SUPPORT_CONTACT || '@Melbetsupporter_bot';

if (!CHANNEL_ID || !CHANNEL_URL) {
    console.warn('BOT_CHANNEL_ID and BOT_CHANNEL_URL must be set to enforce mandatory channel joining.');
}

const bot = new Telegraf(BOT_TOKEN);
bot.use(session());

bot.use(async (ctx, next) => {
    if (!ctx.from || String(ctx.from.id) === '') return next();
    if (ADMIN_IDS.has(String(ctx.from.id))) return next();
    try {
        const snap = await db.collection('users').doc(String(ctx.from.id)).get();
        if (snap.exists && snap.data().blocked) return ctx.reply('⛔ የመለያዎ መዳረሻ በአድሚን ታግዷል።');
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
    );
}

function askForContact(ctx) {
    return ctx.reply(
        '✅ MELBET ቻናሉን በትክክል ተቀላቅለዋል።\n\nምዝገባውን ለማጠናቀቅ የራስዎን ስልክ ቁጥር ያጋሩ።',
        Markup.keyboard([
            [Markup.button.contactRequest('📱 ስልክ ቁጥሮን አጋራ')]
        ]).resize().oneTime()
    );
}

async function showMainMenu(ctx) {
    const replyMarkup = {
        inline_keyboard: [
            [
                {
                    text: "💼 የኔ ሂሳብ (Account)",
                    callback_data: "account",
                    style: "primary"
                },
                {
                    text: "🎁 ጋብዝ እና አግኝ (Refer)",
                    callback_data: "refer",
                    style: "primary"
                }
            ],
            [
                {
                    text: "📜 የጨዋታ ህጎች (Rules)",
                    callback_data: "rules",
                    style: "primary"
                },
                {
                    text: "🎧 እርዳታ (Support)",
                    callback_data: "support",
                    style: "primary"
                }
            ],
            [
                {
                    text: "🎮 Play Melbet Bingo",
                    web_app: {
                        url: WEBAPP_URL
                    },
                    style: "primary"
                }
            ]
        ]
    };

    if (isAdmin(ctx)) {
        replyMarkup.inline_keyboard.push([
            {
                text: "🛠 Admin Panel",
                web_app: {
                    url: `${WEBAPP_URL}/admin`
                },
                style: "primary"
            }
        ]);
    }

    return ctx.reply(
        "✅ ምዝገባዎ ተሳክቷል! እባክዎ ከታች ያሉትን አማራጮች ይምረጡ።",
        {
            reply_markup: replyMarkup
        }
    );
}


async function showMainMenu(ctx) {
    // ከዚህ በፊት ያለው replyMarkup ኮድ እዚህ ይቀጥላል

    await ctx.reply(
        '✅ ምዝገባዎ ተሳክቷል! እባክዎ ከታች ካሉት አማራጮች ይምረጡ።',
        { reply_markup: replyMarkup }
    );
}
// Handle callback queries for the primary inline menu buttons (ዳታቤዝ እና ሌሎች ሎጂኮች)

bot.on('callback_query', async (ctx) => {
    const action = ctx.callbackQuery?.data;
    const chatId = ctx.callbackQuery?.message?.chat?.id;
    const userId = String(ctx.from.id);

    if (!action || !chatId) return;

    if (
        action === 'verify_channel' ||
        action.startsWith('dp_') ||
        action.startsWith('wd_')
    ) {
        return;
    }

    await ctx.answerCbQuery().catch(() => {});

    if (action === 'account') {
        const snap = await db.collection('users').doc(userId).get();

        if (!snap.exists) {
            return ctx.telegram.sendMessage(
                chatId,
                'መጀመሪያ /start በመላክ ይመዝገቡ።'
            );
        }

        const d = snap.data();

        return ctx.telegram.sendMessage(
            chatId,
            `👤 የእርስዎ ሂሳብ\n` +
            `💵 Main Balance: ${money(d.balance)}\n` +
            `🎁 Bonus Balance: ${money(d.bonus)}\n` +
            `💳 Deposit አድርገዋል: ${d.has_deposited ? 'አዎ' : 'ገና አይደለም'}`
        );
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
        );
    }

    if (action === 'rules') {
        return ctx.telegram.sendMessage(
            chatId,
            '🎮 የBingo ህጎች\n' +
            '• አንድ ካርድ 10 ETB ነው።\n' +
            '• Bonus Balance ቀድሞ ይቀነሳል፤ ቀሪው ከMain Balance ይቀነሳል።\n' +
            '• የጨዋታ ሽልማት ወደ Main Balance ይገባል።\n' +
            '• ገንዘብ ለማውጣት ቢያንስ አንድ ጊዜ Deposit ማድረግ ያስፈልጋል።'
        );
    }

    if (action === 'support') {
        return ctx.telegram.sendMessage(
            chatId,
            `🎧 እርዳታ ለማግኘት ${SUPPORT_CONTACT} ያነጋግሩ።`
        );
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

        ctx.reply('⚠️ ጊዜያዊ ችግር ተፈጥሯል። እባክዎ /start እንደገና ይላኩ።');
    }
});


bot.action('verify_channel', async ctx => {
    await ctx.answerCbQuery();

    if (!await isChannelMember(ctx)) {
        return ctx.reply('❌ ገና ቻናሉን አልተቀላቀሉም። ቻናሉን ይቀላቀሉና እንደገና ይሞክሩ።');
    }

    const doc = await db.collection('users').doc(String(ctx.from.id)).get();

    if (!doc.exists || !doc.data().phone_number) {
        return askForContact(ctx);
    }

    await db.collection('users').doc(String(ctx.from.id)).set({
        channel_joined: true
    }, { merge: true });

    await showMainMenu(ctx);
});

bot.on('contact', async ctx => {
    try {
        const contact = ctx.message.contact;

        if (String(contact.user_id) !== String(ctx.from.id)) {
            return ctx.reply('⚠️ እባክዎ የራስዎን ስልክ ቁጥር ብቻ ያጋሩ።');
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

        ctx.reply('⚠️ ምዝገባው አልተሳካም። እባክዎ እንደገና ይሞክሩ።');
    }
});

async function beginWalletFlow(ctx, action) {
    if (action === 'deposit') {
        ctx.session.flow = 'deposit_amount';
        return ctx.reply(`💰 ሂሳብ ለመሙላት የክፍያ አማራጭ: Telebirr\n\n${DEPOSIT_INSTRUCTIONS}\n\nእባክዎ የሚፈልጉትን መጠን በETB ያስገቡ (አነስተኛ ${DEPOSIT_MINIMUM} ETB)።\n/cancel ለመሰረዝ።`);
    }

    const ref = db.collection('users').doc(String(ctx.from.id));
    const snap = await ref.get();

    if (!snap.exists || !snap.data().has_deposited) {
        return ctx.reply('⛔ ገንዘብ ለማውጣት መጀመሪያ ቢያንስ አንድ ጊዜ Deposit ማድረግ አለብዎት።');
    }

    ctx.session.flow = 'withdraw_amount';

    return ctx.reply(`📤 ለማውጣት የሚፈልጉትን መጠን በETB ያስገቡ።\nዝቅተኛ Withdrawal: ${money(WITHDRAW_MINIMUM)}\nMain Balance: ${money(snap.data().balance)}\n/cancel ለመሰረዝ።`);
}

bot.command('cancel', ctx => {
    ctx.session.flow = null;
    ctx.session.depositAmount = null;
    ctx.session.withdrawAmount = null;
    ctx.session.withdrawName = null;
    ctx.session.withdrawAccount = null;

    ctx.reply('ተሰርዟል።');
});

bot.on('text', async ctx => {
    const flow = ctx.session?.flow;

    if (!flow || ctx.message.text.startsWith('/')) return;

    const amount = Number(ctx.message.text.replace(',', '.'));

    if (flow === 'deposit_proof') {
        const amountProof = Number(ctx.session.depositAmount || 0);

        if (!amountProof) {
            ctx.session.flow = null;
            return ctx.reply('Deposit እንደገና ይጀምሩ።');
        }

        const proofRef = db.collection('deposit_requests').doc();

        await proofRef.set({
            user_id: String(ctx.from.id),
            amount: amountProof,
            receipt_text: ctx.message.text.slice(0, 1500),
            status: 'pending',
            created_at: Date.now()
        });

        ctx.session.flow = null;
        ctx.session.depositAmount = null;

        await ctx.reply('✅ የክፍያ SMS/Transaction መረጃዎ ተልኳል። አድሚኑ ካረጋገጠው በኋላ Bonus Balance ይጨመራል።');

        for (const aid of ADMIN_ID_LIST) {
            await bot.telegram.sendMessage(
                aid,
                `📥 Deposit request\nUser: ${ctx.from.id}\nAmount: ${money(amountProof)}\nSMS: ${ctx.message.text.slice(0, 1000)}\nRequest: ${proofRef.id}`,
                Markup.inlineKeyboard([
                    [
                        Markup.button.callback('✅ Approve', `dp_ok_${proofRef.id}`),
                        Markup.button.callback('❌ Reject', `dp_no_${proofRef.id}`)
                    ]
                ])
            ).catch(() => {});
        }

        return;
    }

    if (flow === 'withdraw_details') {
        const parts = ctx.message.text.trim().split(/\s*\|\s*/);

        if (parts.length < 2 || parts[0].length < 2 || parts[1].length < 5) {
            return ctx.reply('እባክዎ በዚህ ቅርጽ ይላኩ፦ ስም | Telebirr ቁጥር\nምሳሌ: Natnael | 09XXXXXXXX');
        }

        ctx.session.withdrawName = parts[0].slice(0, 80);
        ctx.session.withdrawAccount = parts[1].slice(0, 40);
        ctx.session.flow = 'withdraw_confirm';

        return ctx.reply(`እባክዎ የWithdrawal መረጃዎን ያረጋግጡ፦\nስም: ${ctx.session.withdrawName}\nTelebirr: ${ctx.session.withdrawAccount}\n\nለመቀጠል CONFIRM ይጻፉ፣ ለመሰረዝ /cancel ይጻፉ።`);
    }

    if (flow === 'withdraw_confirm') {
        if (ctx.message.text.trim().toUpperCase() !== 'CONFIRM') {
            return ctx.reply('ለማረጋገጥ CONFIRM ይጻፉ ወይም /cancel ይጠቀሙ።');
        }

        const uid = String(ctx.from.id);
        const amount2 = Number(ctx.session.withdrawAmount || 0);
        const userRef = db.collection('users').doc(uid);
        const requestRef = db.collection('withdrawal_requests').doc();

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

            await ctx.reply('✅ የWithdrawal ጥያቄዎ ወደ Admin Panel ተልኳል። አድሚኑ ካጸደቀ በኋላ ክፍያውን በTelebirr ይልካል።');

            const saved = await requestRef.get();

            for (const aid of ADMIN_ID_LIST) {
                await bot.telegram.sendMessage(
                    aid,
                    `📤 Withdrawal request\nUser: ${uid}\nName: ${saved.data()?.payout_name}\nTelebirr: ${saved.data()?.payout_account}\nAmount: ${money(amount2)}\nRequest: ${requestRef.id}`,
                    Markup.inlineKeyboard([
                        [
                            Markup.button.callback('✅ Approve', `wd_ok_${requestRef.id}`),
                            Markup.button.callback('❌ Reject', `wd_no_${requestRef.id}`)
                        ]
                    ])
                ).catch(() => {});
            }

        } catch (e) {
            ctx.session.flow = null;
            ctx.session.withdrawAmount = null;

            return ctx.reply(
                e.message === 'INSUFFICIENT_BALANCE'
                    ? '❌ Main Balance በቂ አይደለም።'
                    : '⚠️ Withdrawal አልተሳካም።'
            );
        }

        return;
    }

    if (flow === 'deposit_amount' || flow === 'withdraw_amount') {
        if (!Number.isFinite(amount) || amount <= 0 || amount > 1000000) {
            return ctx.reply('እባክዎ ትክክለኛ የETB መጠን ያስገቡ።');
        }
    }

    if (flow === 'deposit_amount') {
        if (amount < DEPOSIT_MINIMUM) {
            return ctx.reply(`❌ አነስተኛ Deposit ${DEPOSIT_MINIMUM} ETB ነው። እባክዎ እንደገና ያስገቡ።`);
        }

        ctx.session.flow = null;
        ctx.session.depositAmount = Math.round(amount * 100) / 100;
        ctx.session.flow = 'deposit_proof';

        return ctx.reply(
            `የDeposit መጠን ${money(amount)} ተቀብለናል። እባክዎ የክፍያ SMS ጽሑፍ ወይም የደረሰኝ ፎቶ (Screenshot) ይላኩ።`
        );
    }

    if (flow === 'withdraw_amount') {
        if (amount < WITHDRAW_MINIMUM) {
            return ctx.reply(`❌ ዝቅተኛ Withdrawal ${WITHDRAW_MINIMUM} ETB ነው።`);
        }

        const amount2 = Math.round(amount * 100) / 100;
        const snap = await db.collection('users').doc(String(ctx.from.id)).get();

        if (!snap.exists || Number(snap.data().balance || 0) < amount2) {
            return ctx.reply('❌ Main Balance በቂ አይደለም።');
        }

        ctx.session.withdrawAmount = amount2;
        ctx.session.flow = 'withdraw_details';

        return ctx.reply('የTelebirr ተቀባይ ስምዎን እና ቁጥርዎን በዚህ ቅርጽ ይላኩ፦\nስም | 09XXXXXXXX');
    }
});

bot.on('photo', async ctx => {
    if (ctx.session?.flow !== 'deposit_proof') return;

    const amount = Number(ctx.session.depositAmount || 0);

    if (!amount) {
        ctx.session.flow = null;
        return ctx.reply('እባክዎ Deposit እንደገና ይጀምሩ።');
    }

    const ref = db.collection('deposit_requests').doc();

    await ref.set({
        user_id: String(ctx.from.id),
        amount,
        photo_file_id: ctx.message.photo.at(-1).file_id,
        status: 'pending',
        created_at: Date.now()
    });

    ctx.session.flow = null;
    ctx.session.depositAmount = null;

    await ctx.reply(
        '✅ የDeposit ማረጋገጫዎ ተልኳል። አድሚኑ ካረጋገጠው በኋላ Bonus Balance ይጨመራል።'
    );

    for (const aid of ADMIN_ID_LIST) {
        await bot.telegram.sendPhoto(
            aid,
            ctx.message.photo.at(-1).file_id,
            {
                caption:
                    `📥 Deposit request\n` +
                    `User: ${ctx.from.id}\n` +
                    `Amount: ${money(amount)}\n` +
                    `Request: ${ref.id}`,
                ...Markup.inlineKeyboard([
                    [
                        Markup.button.callback('✅ Approve', `dp_ok_${ref.id}`),
                        Markup.button.callback('❌ Reject', `dp_no_${ref.id}`)
                    ]
                ])
            }
        );
    }
});

async function reviewRequest(ctx, type, id, approve) {
    if (!isAdmin(ctx)) {
        return ctx.answerCbQuery('Not authorized', { show_alert: true });
    }

    const collection = type === 'deposit'
        ? 'deposit_requests'
        : 'withdrawal_requests';

    const reqRef = db.collection(collection).doc(id);

    try {
        await db.runTransaction(async tx => {
            const reqSnap = await tx.get(reqRef);

            if (!reqSnap.exists || reqSnap.data().status !== 'pending') {
                throw new Error('ALREADY_PROCESSED');
            }

            const r = reqSnap.data();

            const userRef = db.collection('users').doc(String(r.user_id));
            const userSnap = await tx.get(userRef);

            if (!userSnap.exists) throw new Error('USER_NOT_FOUND');

            const d = userSnap.data();

            if (type === 'deposit' && approve) {
                tx.update(userRef, {
                    bonus: Number(d.bonus || 0) + Number(r.amount),
                    has_deposited: true,
                    first_deposit_at: d.first_deposit_at || Date.now(),
                    transactions: [
                        ...(d.transactions || []),
                        {
                            type: 'deposit',
                            wallet: 'bonus',
                            amount: Number(r.amount),
                            request_id: id,
                            timestamp: new Date().toISOString()
                        }
                    ]
                });
            }

            if (type === 'withdrawal' && !approve) {
                tx.update(userRef, {
                    balance: Number(d.balance || 0) + Number(r.amount),
                    transactions: [
                        ...(d.transactions || []),
                        {
                            type: 'withdrawal_refund',
                            amount: Number(r.amount),
                            request_id: id,
                            timestamp: new Date().toISOString()
                        }
                    ]
                });
            }

            tx.update(reqRef, {
                status: approve ? 'approved' : 'rejected',
                reviewed_at: Date.now(),
                reviewed_by: String(ctx.from.id)
            });
        });

        await ctx.answerCbQuery(approve ? 'Approved' : 'Rejected');

        await ctx.editMessageCaption(
            `${ctx.callbackQuery.message.caption || ''}\n\nStatus: ${approve ? 'APPROVED' : 'REJECTED'}`
        ).catch(() =>
            ctx.editMessageText(
                `${ctx.callbackQuery.message.text || ''}\n\nStatus: ${approve ? 'APPROVED' : 'REJECTED'}`
            ).catch(() => {})
        );

        const snap = await reqRef.get();

        const reviewed = snap.data() || {};
        const amountLabel = money(reviewed.amount || 0);

        const notice = type === 'deposit'
            ? `${approve ? '✅ DEPOSIT APPROVED' : '❌ DEPOSIT REJECTED'}\nAmount: ${amountLabel}\nReference: ${reviewed.reference || id}\n${approve ? 'Bonus Balance ላይ ተጨምሯል።' : 'እባክዎ የክፍያ መረጃውን ያረጋግጡ።'}`
            : `${approve ? '✅ WITHDRAWAL APPROVED' : '❌ WITHDRAWAL REJECTED'}\nAmount: ${amountLabel}\nRequest ID: ${id}\n${approve ? 'Admin በTelebirr ክፍያውን ይልካል።' : 'ገንዘቡ ወደ Main Balance ተመልሷል።'}`;

        await bot.telegram.sendMessage(
            String(reviewed.user_id),
            notice
        ).catch(err => console.warn('wallet review notification failed:', err.message));

    } catch (e) {
        await ctx.answerCbQuery(
            e.message === 'ALREADY_PROCESSED'
                ? 'Already processed'
                : 'Could not process',
            { show_alert: true }
        );
    }
}

bot.action(/^dp_ok_(.+)$/, ctx =>
    reviewRequest(ctx, 'deposit', ctx.match[1], true)
);

bot.action(/^dp_no_(.+)$/, ctx =>
    reviewRequest(ctx, 'deposit', ctx.match[1], false)
);

bot.action(/^wd_ok_(.+)$/, ctx =>
    reviewRequest(ctx, 'withdrawal', ctx.match[1], true)
);

bot.action(/^wd_no_(.+)$/, ctx =>
    reviewRequest(ctx, 'withdrawal', ctx.match[1], false)
);

bot.launch()
    .then(() => console.log('Telegram Bot polling started.'))
    .catch(err => console.error('Telegram bot launch failed:', err.message));

bot.catch((err, ctx) =>
    console.error('Telegram bot handler error:', err, 'update:', ctx.updateType)
);

module.exports = bot;
