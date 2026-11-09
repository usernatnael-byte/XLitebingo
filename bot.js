const { Telegraf, Markup } = require('telegraf');
const admin = require('firebase-admin');

const BOT_TOKEN = process.env.BOT_TOKEN || "8747562686:AAGQCIOwD3ahfjVY21PY4gvftQCtxaq0UNA";
const WEBAPP_URL = process.env.WEBAPP_URL || "https://xlitebingo.onrender.com";
const ADMIN_ID = 7396414604;

const bot = new Telegraf(BOT_TOKEN);
const db = admin.firestore();

bot.start(async (ctx) => {
    const userId = ctx.chat.id;
    const firstName = ctx.from.first_name;
    const username = ctx.from.username || "";

    const userRef = db.collection("users").document(String(userId));
    const userDoc = await userRef.get();

    if (!userDoc.exists) {
        await userRef.set({
            telegram_id: String(userId),
            first_name: firstName,
            username: username,
            balance: 0.0,
            created_at: admin.firestore.FieldValue.serverTimestamp()
        });
    }

    const userData = userDoc.exists ? userDoc.data() : {};

    if (!userData.phone_number) {
        return ctx.reply(
            `ሰላም ${firstName}! ወደ ቢንጎ ቦት እንኳን ደህና መጡ።\n\nእባክዎ መዝገቡን ለማጠናቀቅ የስልክ ቁጥርዎን ያጋሩ፦`,
            Markup.keyboard([
                [Markup.button.contactRequest("📱 ስልክ ቁጥር አጋራ (Share Phone)")]
            ]).resize().oneTime()
        );
    }

    sendMainMenu(ctx);
});

function sendMainMenu(ctx) {
    const menu = Markup.keyboard([
        ["💼 የኔ ሂሳብ (Account)", "🎁 ጋብዝ እና አግኝ (Refer)"],
        ["📥 ገቢ (Deposit)", "📤 ወጪ (Withdraw)"],
        ["🎧 እርዳታ ማዕከል (Help & Support)"]
    ]).resize();

    ctx.reply("እንኳን ደህና መጡ! ከታች ያለውን በመጫወት ይጀምሩ፡", menu);
    ctx.reply("🎮 ጨዋታውን ለመክፈት:", Markup.inlineKeyboard([
        [Markup.button.webApp("🎮 Play Bingo", WEBAPP_URL)]
    ]));
}

bot.on('contact', async (ctx) => {
    const contact = ctx.message.contact;
    if (contact.user_id !== ctx.from.id) {
        return ctx.reply("⚠️ እባክዎ የራስዎን ስልክ ቁጥር ብቻ ያጋሩ።");
    }

    const userId = String(ctx.chat.id);
    let phoneNumber = contact.phone_number;
    if (!phoneNumber.startsWith("+")) phoneNumber = "+" + phoneNumber;

    await db.collection("users").document(userId).set({ phone_number: phoneNumber }, { merge: true });

    ctx.reply("✅ የስልክ ቁጥርዎ በተሳካ ሁኔታ ተመዝግቧል!");
    sendMainMenu(ctx);
});

bot.hears("💼 የኔ ሂሳብ (Account)", async (ctx) => {
    const userId = String(ctx.chat.id);
    const doc = await db.collection("users").document(userId).get();
    const data = doc.exists ? doc.data() : {};
    
    const balance = data.balance || 0.0;
    const bonus = data.bonus || 0.0;
    const phone = data.phone_number || "አልተመዘገበም";

    ctx.reply(
        `👤 *የእርስዎ ፕሮፋይል*\n───────────────\n` +
        `🔹 ስልክ: ${phone}\n` +
        `💰 ዋና ሂሳብ: ${balance.toFixed(2)} ETB\n` +
        `🎁 የጨዋታ ሂሳብ: ${bonus.toFixed(2)} ETB`,
        { parse_mode: "Markdown" }
    );
});

bot.hears("🎧 እርዳታ ማዕከል (Help & Support)", (ctx) => {
    ctx.reply("🎧 ማንኛውም ጥያቄ ካለዎት እባክዎ ያነጋግሩን:\n📩 @zeid369");
});

bot.launch();
console.log("🤖 Telegram Bot is running...");
                                       
