import os
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, db as rtdb
import telebot
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

# ==========================================
# ⚙️ CONFIGURATION & INITIALIZATION
# ==========================================
TOKEN = "8691863316:AAFsrM6GVNXMfMIfi7B49cS0ST-bR_xyQPg"
WEBAPP_URL = "https://xlitebingo-1.onrender.com"
ADMIN_ID = 7396414604  # የእርስዎ አድሚን Telegram ID

# Firebase Realtime Database ማስጀመር
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://litebingo-513a9-default-rtdb.firebaseio.com/'
    })
print("✅ ቦቱ ከ Firebase Realtime Database ጋር ተገናኝቷል!")

bot = telebot.TeleBot(TOKEN)

# ==========================================
# 🛠️ HELPER FUNCTIONS
# ==========================================
def get_main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_account = KeyboardButton(text="💼 የኔ ሂሳብ (Account)")
    btn_refer = KeyboardButton(text="🎁 ጋብዝ እና አግኝ (Refer)")
    btn_deposit = KeyboardButton(text="📥 ገቢ (Deposit)")
    btn_withdraw = KeyboardButton(text="📤 ወጪ (Withdraw)")
    btn_help = KeyboardButton(text="🎧 እርዳታ ማዕከል (Help & Support)")
    markup.add(btn_account, btn_refer, btn_deposit, btn_withdraw, btn_help)
    return markup

def is_admin(user_id):
    return user_id == ADMIN_ID


# ==========================================
# 🤖 BOT COMMANDS & HANDLERS
# ==========================================

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = str(message.chat.id)
    first_name = message.from_user.first_name
    username = message.from_user.username or ""

    user_ref = rtdb.reference(f"users/{user_id}")
    user_data = user_ref.get()

    args = message.text.split()

    if not user_data:
        referred_by = None
        if len(args) > 1 and args[1].startswith("ref_"):
            try:
                referrer_id = args[1].replace("ref_", "")
                if referrer_id != user_id:
                    referred_by = referrer_id
            except ValueError:
                pass

        user_data = {
            "telegram_id": user_id,
            "first_name": first_name,
            "username": username,
            "balance": 0.0,
            "bonus": 0.0,
            "total_games_played": 0,
            "total_winnings": 0.0,
            "referred_by": referred_by,
            "created_at": datetime.utcnow().isoformat(),
            "transactions": []
        }
        user_ref.set(user_data)

    if "phone_number" not in user_data or not user_data["phone_number"]:
        markup = ReplyKeyboardMarkup(row_width=1, resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton(text="📱 ስልክ ቁጥር አጋራ (Share Phone Number)", request_contact=True))
        bot.send_message(
            message.chat.id,
            f"ሰላም {first_name}! እንኳን ወደ Lite Bingo በደህና መጡ። 🎮\nምዝገባውን ለማጠናቀቅ እባክዎ ከታች ያለውን ቁልፍ በመጫን ስልክ ቁጥርዎን ያጋሩ:",
            reply_markup=markup,
        )
        return

    bot.send_message(
        message.chat.id,
        f"እንኳን ደህና መጡ፣ {first_name}!",
        reply_markup=get_main_menu()
    )

    inline_markup = InlineKeyboardMarkup()
    inline_markup.add(InlineKeyboardButton("🎮 Play Lite Bingo", web_app=WebAppInfo(url=WEBAPP_URL)))
    bot.send_message(
        message.chat.id,
        "ጨዋታውን ለመክፈት ከታች ያለውን ቁልፍ ይጫኑ፦",
        reply_markup=inline_markup
    )

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    if message.contact is not None:
        if message.contact.user_id != message.from_user.id:
            bot.send_message(message.chat.id, "⚠️ እባክዎን የራስዎን ትክክለኛ ስልክ ቁጥር ብቻ ያጋሩ።")
            return
        
        user_id = str(message.chat.id)
        phone_number = message.contact.phone_number
        if not phone_number.startswith("+"):
            phone_number = "+" + phone_number

        user_ref = rtdb.reference(f"users/{user_id}")
        user_ref.update({"phone_number": phone_number})

        bot.send_message(
            message.chat.id,
            "✅ ስልክ ቁጥርዎ በተሳካ ሁኔታ ተመዝግቧል!",
            reply_markup=get_main_menu()
        )

        inline_markup = InlineKeyboardMarkup()
        inline_markup.add(InlineKeyboardButton("🎮 Play Lite Bingo", web_app=WebAppInfo(url=WEBAPP_URL)))
        bot.send_message(
            message.chat.id,
            "አሁን ጨዋታውን መክፈት ይችላሉ፦",
            reply_markup=inline_markup
        )

# --- 💼 ACCOUNT PROFILE ---
@bot.message_handler(func=lambda message: message.text == "💼 የኔ ሂሳብ (Account)")
def show_profile(message):
    user_name = message.from_user.first_name
    user_id = str(message.chat.id)

    user_data = rtdb.reference(f"users/{user_id}").get() or {}
    
    play_balance = float(user_data.get("bonus", 0.0) or 0.0)
    main_balance = float(user_data.get("balance", 0.0))
    phone = user_data.get("phone_number", "አልተመዘገበም")

    profile_msg = (
        "👤 *የእርስዎ ፕሮፋይል (Your Profile)*\n"
        "───────────────\n"
        f"🔹 *ስም (Name):* {user_name}\n"
        f"🔹 *ስልክ (Phone):* {phone}\n\n"
        f"💰 *የጨዋታ ሂሳብ (Play Balance):* {play_balance:.2f} ETB\n"
        f"🏦 *ዋና ሂሳብ (Main Balance):* {main_balance:.2f} ETB\n"
        "───────────────\n"
        "💡 *ወደ ሂሳብዎ ብር ለመጨመር '📥 ገቢ (Deposit)' የሚለውን ይጫኑ::*"
    )
    bot.send_message(message.chat.id, profile_msg, parse_mode="Markdown")

# --- 🎁 REFERRAL SYSTEM ---
@bot.message_handler(func=lambda message: message.text == "🎁 ጋብዝ እና አግኝ (Refer)")
def refer_handler(message):
    user_id = str(message.chat.id)
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    data = rtdb.reference(f"users/{user_id}").get() or {}
    count = data.get("referrals_count", 0)
    earnings = data.get("referral_earnings", 0.0)

    text = (
        "🎁 *ጓደኞችዎን በመጋበዝ ቦነስ ያግኙ!*\n\n"
        "የእርስዎን ልዩ የጋበዣ ሊንክ ለጓደኞችዎ በማጋራት ተጠቃሚ ይሁኑ።\n\n"
        f"🔗 *የእርስዎ ሊንክ:* `{ref_link}`\n\n"
        f"👥 *የጋበዟቸው ሰዎች ብዛት:* {count}\n"
        f"💰 *ካገኙት ቦነስ:* {earnings:.2f} ETB"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# --- 📥 DEPOSIT FLOW (ገቢ) ---
@bot.message_handler(func=lambda message: message.text == "📥 ገቢ (Deposit)")
def deposit_step_1_method(message):
    bot.clear_step_handler_by_chat_id(message.chat.id)
    
    markup = InlineKeyboardMarkup(row_width=2)
    btn_telebirr = InlineKeyboardButton("Telebirr 📱", callback_data="dep_telebirr")
    btn_cbe = InlineKeyboardButton("CBEBirr 🏦", callback_data="dep_cbebirr")
    markup.add(btn_telebirr, btn_cbe)
    
    bot.send_message(
        message.chat.id, 
        "💰 ሂሳብ ለመሙላት የሚጠቀሙበትን የክፍያ አማራጭ ይምረጡ፡-", 
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data in ['dep_telebirr', 'dep_cbebirr'])
def deposit_step_2_amount(call):
    method = "Telebirr" if call.data == "dep_telebirr" else "CBEBirr"
    bot.answer_callback_query(call.id)
    
    msg = bot.send_message(
        call.message.chat.id,
        f"እባክዎ በ {method} ማስገባት የሚፈልጉትን የብር መጠን ያስገቡ\n*(አነስተኛ መጠን: 50 ETB)*",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_deposit_amount, method)

def process_deposit_amount(message, method):
    if message.text in ["💼 የኔ ሂሳብ (Account)", "📥 ገቢ (Deposit)", "📤 ወጪ (Withdraw)", "🎁 ጋብዝ እና አግኝ (Refer)", "🎧 እርዳታ ማዕከል (Help & Support)"]:
        bot.send_message(message.chat.id, "ሂደቱ ተቋርጧል።")
        return

    try:
        amount = float(message.text)
        if amount < 50:
            msg = bot.send_message(message.chat.id, "⚠️ ይቅርታ፣ ማስገባት የሚችሉት አነስተኛ መጠን **50 ETB** ነው።\nእባክዎ ትክክለኛ መጠን ያስገቡ፦", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_deposit_amount, method)
        else:
            instructions = (
                f"መሙላት የፈለጉት መጠን: **{amount:g} ETB**\n\n"
                f"እባክዎ ከታች ወዳለው የ{method} አካውንት ብሩን ያስገቡ።\n"
                f"👤 ስም: **Zeid**\n"
                f"📱 አካውንት: **0935084226**\n\n"
                f"ብሩን ከላኩ በኋላ የግብይቱን **የደረሰኝ ፎቶ (Screenshot)** ወይም **የባንክ SMS** እዚህ ይላኩልን፦"
            )
            msg = bot.send_message(message.chat.id, instructions, parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_deposit_proof, method, amount)
    except ValueError:
        msg = bot.send_message(message.chat.id, "⚠️ እባክዎ ትክክለኛ ቁጥር ብቻ ያስገቡ (ለምሳሌ፦ 100):")
        bot.register_next_step_handler(msg, process_deposit_amount, method)

def process_deposit_proof(message, method, amount):
    if message.text in ["💼 የኔ ሂሳብ (Account)", "📥 ገቢ (Deposit)", "📤 ወጪ (Withdraw)", "🎁 ጋብዝ እና አግኝ (Refer)", "🎧 እርዳታ ማዕከል (Help & Support)"]:
        bot.send_message(message.chat.id, "ሂደቱ ተቋርጧል።")
        return

    bot.send_message(
        message.chat.id,
        "✅ የክፍያ ማረጋገጫዎ ደርሷል! አድሚኑ አረጋግጦ ሂሳብዎ ላይ እስኪጨምር በደግነት ይጠብቁ።"
    )

    if ADMIN_ID:
        try:
            user_info = f"👤 ተጠቃሚ: {message.from_user.first_name} (ID: `{message.chat.id}`)"
            admin_text = f"📥 **አዲስ የገቢ (Deposit) ጥያቄ!**\n\n{user_info}\n🔹 ዘዴ: {method}\n💰 መጠን: {amount} ETB\n\n*ሂሳብ ለመጨመር ይህንን ኮድ ይጠቀሙ:*\n`/addbalance {message.chat.id} {amount}`"
            bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown")
            bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
        except Exception as e:
            print(f"Admin forward error: {e}")

# --- 📤 WITHDRAW FLOW (ወጪ) ---
@bot.message_handler(func=lambda message: message.text == "📤 ወጪ (Withdraw)")
def withdraw_step_1_method(message):
    bot.clear_step_handler_by_chat_id(message.chat.id)
    msg = bot.send_message(
        message.chat.id,
        "📤 ማውጣት የሚፈልጉትን የብር መጠን ያስገቡ፦\n*(አነስተኛ ማውጫ: 100 ETB)*"
    )
    bot.register_next_step_handler(msg, process_withdraw_amount)

def process_withdraw_amount(message):
    try:
        amount = float(message.text)
        if amount < 100:
            msg = bot.send_message(message.chat.id, "⚠️ አነስተኛ ማውጣት የሚችሉት መጠን 100 ETB ነው። እባክዎ እንደገና ያስገቡ፦")
            bot.register_next_step_handler(msg, process_withdraw_amount)
            return
        
        msg = bot.send_message(
            message.chat.id,
            "📱 ገንዘቡ የሚላክበትን የስልክ ቁጥር እና የባንክ ስም ያስገቡ (ለምሳሌ: Telebirr - 09********):"
        )
        bot.register_next_step_handler(msg, process_withdraw_account, amount)
    except ValueError:
        msg = bot.send_message(message.chat.id, "⚠️ እባክዎ ትክክለኛ ቁጥር ያስገቡ፦")
        bot.register_next_step_handler(msg, process_withdraw_amount)

def process_withdraw_account(message, amount):
    acc_info = message.text
    user_id = message.chat.id
    
    bot.send_message(
        user_id,
        f"✅ የ {amount} ETB የወጪ ጥያቄዎ በተሳካ ሁኔታ ተልኳል! በቅርብ ጊዜ ይረጋገጣል።"
    )
    
    if ADMIN_ID:
        try:
            bot.send_message(
                ADMIN_ID,
                f"📤 **አዲስ የወጪ (Withdrawal) ጥያቄ!**\n\n👤 ተጠቃሚ ID: `{user_id}`\n💰 መጠን: {amount} ETB\n📱 አካውንት: {acc_info}\n\n*ሂሳብ ለመቀነስ ይህንን ኮድ ይጠቀሙ:*\n`/deductbalance {user_id} {amount}`",
                parse_mode="Markdown"
            )
        except Exception:
            pass

# --- 🎧 HELP & SUPPORT ---
@bot.message_handler(func=lambda message: message.text == "🎧 እርዳታ ማዕከል (Help & Support)")
def help_handler(message):
    help_text = (
        "🎧 *እርዳታ እና ድጋፍ (Help & Support)*\n\n"
        "ጨዋታውን በሚጫወቱበት ጊዜ ወይም በግንኙነት ላይ ጥያቄ ካሎት ከታች ባለው አድራሻ ያግኙን።\n\n"
        "👨‍💻 አስተዳዳሪ: @Zeid_Admin\n"
        "📞 ስልክ ድጋፍ: 0935084226"
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")


# ==========================================
# 👑 ADMIN CONTROL COMMANDS
# ==========================================

# 1. ዲፖዚት ማጽደቂያ - ሂሳብ መጨመር (/addbalance USER_ID AMOUNT)
@bot.message_handler(commands=['addbalance'])
def add_balance(message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, target_user_id, amount = message.text.split()
        amount = float(amount)

        ref = rtdb.reference(f"users/{target_user_id}")
        data = ref.get()
        if not data:
            bot.reply_to(message, "❌ ይህ ተጠቃሚ በዳታቤዝ ውስጥ አልተገኘም!")
            return

        current_bal = float(data.get("balance", 0.0))
        new_bal = current_bal + amount

        txs = data.get("transactions", [])
        txs.append({
            "type": "deposit",
            "amount": amount,
            "timestamp": datetime.utcnow().isoformat()
        })

        ref.update({"balance": new_bal, "transactions": txs})

        bot.reply_to(message, f"✅ **Deposit Approved!**\n\n👤 User ID: `{target_user_id}`\n💰 የተጨመረ: `{amount:.2f} ETB`\n💵 አዲሱ ባላንስ: `{new_bal:.2f} ETB`", parse_mode="Markdown")
        bot.send_message(target_user_id, f"🎉 **ዲፖዚት ተጸድቋል!**\n\nወደ ሂሳብዎ **{amount:.2f} ETB** ገቢ ሆኗል።\nአሁን ያለው ጠቅላላ ባላንስ: **{new_bal:.2f} ETB**", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, "❌ **ስህተት!**\nአጠቃቀም: `/addbalance USER_ID AMOUNT`\nምሳሌ: `/addbalance 123456789 100`", parse_mode="Markdown")

# 2. ዊዝድሮው ማጽደቂያ - ሂሳብ መቀነስ (/deductbalance USER_ID AMOUNT)
@bot.message_handler(commands=['deductbalance'])
def deduct_balance(message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, target_user_id, amount = message.text.split()
        amount = float(amount)

        ref = rtdb.reference(f"users/{target_user_id}")
        data = ref.get()
        if not data:
            bot.reply_to(message, "❌ ይህ ተጠቃሚ በዳታቤዝ ውስጥ አልተገኘም!")
            return

        current_bal = float(data.get("balance", 0.0))
        if current_bal < amount:
            bot.reply_to(message, f"⚠️ ተጠቃሚው በቂ ባላንስ የለውም። ያለው ባላንስ: `{current_bal:.2f} ETB`", parse_mode="Markdown")
            return

        new_bal = current_bal - amount

        txs = data.get("transactions", [])
        txs.append({
            "type": "withdraw",
            "amount": amount,
            "timestamp": datetime.utcnow().isoformat()
        })

        ref.update({"balance": new_bal, "transactions": txs})

        bot.reply_to(message, f"✅ **Withdrawal Approved!**\n\n👤 User ID: `{target_user_id}`\nቀናሽ የተደረገ: `{amount:.2f} ETB`\nቀሪ ባላንስ: `{new_bal:.2f} ETB`", parse_mode="Markdown")
        bot.send_message(target_user_id, f"💸 **ወጪ ገደብ ተፈጽሟል!**\n\nከሂሳብዎ **{amount:.2f} ETB** ወጪ ሆኗል።\nቀሪ ባላንስ: **{new_bal:.2f} ETB**", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, "❌ **ስህተት!**\nአጠቃቀም: `/deductbalance USER_ID AMOUNT`\nምሳሌ: `/deductbalance 123456789 50`", parse_mode="Markdown")

# 3. የተጠቃሚ መረጃ መፈለጊያ (/userinfo USER_ID)
@bot.message_handler(commands=['userinfo'])
def user_info(message):
    if not is_admin(message.from_user.id):
        return
    try:
        _, target_user_id = message.text.split()
        data = rtdb.reference(f"users/{target_user_id}").get()
        if not data:
            bot.reply_to(message, "❌ ተጠቃሚው አልተገኘም!")
            return

        info = f"👤 **የተጠቃሚ መረጃ (User Profile)**\n\n"
        info += f"• **ID:** `{data.get('telegram_id', target_user_id)}`\n"
        info += f"• **ስም:** {data.get('first_name', 'N/A')}\n"
        info += f"• **Username:** @{data.get('username', 'N/A')}\n"
        info += f"• **ስልክ ቁጥር:** `{data.get('phone_number', 'ያልተመዘገበ')}`\n"
        info += f"• **ባላንስ:** `{float(data.get('balance', 0)):.2f} ETB`\n"
        info += f"• **የተጫወተው ጨዋታ:** `{data.get('total_games_played', 0)}` ዙር\n"
        info += f"• **ያሸነፈው መጠን:** `{float(data.get('total_winnings', 0)):.2f} ETB`\n"

        bot.reply_to(message, info, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, "❌ አጠቃቀም: `/userinfo USER_ID`", parse_mode="Markdown")

# 4. አጠቃላይ የሲስተም ስታቲስቲክስ (/stats)
@bot.message_handler(commands=['stats'])
def show_stats(message):
    if not is_admin(message.from_user.id):
        return
    users = rtdb.reference("users").get() or {}
    total_users = len(users)
    total_balance = sum(float(u.get("balance", 0)) for u in users.values())
    total_winnings = sum(float(u.get("total_winnings", 0)) for u in users.values())

    msg = f"📊 **1x Bingo Admin Dashboard**\n\n"
    msg += f"👥 **ጠቅላላ ተጠቃሚዎች:** `{total_users}`\n"
    msg += f"💰 **የተጫዋቾች ባላንስ:** `{total_balance:.2f} ETB`\n"
    msg += f"🏆 **የተከፈለ አጠቃላይ ሽልማት:** `{total_winnings:.2f} ETB`\n"
    bot.reply_to(message, msg, parse_mode="Markdown")


# ==========================================
# 🚀 START BOT POLLING
# ==========================================
if __name__ == "__main__":
    print("🤖 የቴሌግራም ቦቱ በመሥራት ላይ ይገኛል...")
    bot.infinity_polling()
