import telebot
from telebot import types
from datetime import datetime
from threading import Thread
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, request, jsonify, send_file, g
from flask_cors import CORS
import os
import hmac
import hashlib
from functools import wraps
from urllib.parse import urlparse
import time
import re
from collections import defaultdict, deque

from game_engine import GameEngine, TICKET_PRICE, PRIZE_PER_CARTEL, MAX_SELECTION
from wallet_firestore import FirestoreWallet

# Initialize Firebase Connection
cred = credentials.Certificate(os.environ.get("FIREBASE_KEY_PATH", "firebase_key.json"))
firebase_admin.initialize_app(cred)

# Create the database object
db = firestore.client()

# ቴሌግራም ቶከን እና ዌብአፕ ዩአርኤል ከ Environment Variables ማንበብ
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://xlitebingo.onrender.com")
_u = urlparse(WEBAPP_URL)
WEBAPP_ORIGIN = f"{_u.scheme}://{_u.netloc}"
RESET_TOKEN = os.environ.get("RESET_TOKEN", "")  
ADMIN_ID = 7396414604  # የእርስዎን ትክክለኛ የቴሌግራም ID ያስገቡ

bot = telebot.TeleBot(BOT_TOKEN)

def verify_telegram_init_data(init_data: str, bot_token: str) -> bool:
    """ቴሌግራም የላከውን initData ትክክለኛነት ያጣራል።"""
    try:
        from urllib.parse import parse_qsl
        parsed_data = dict(parse_qsl(init_data))
        hash_to_check = parsed_data.pop('hash', None)
        if not hash_to_check:
            return False
        
        data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(parsed_data.items())])
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        return hmac.compare_digest(calculated_hash, hash_to_check)
    except Exception as e:
        return False

def require_telegram_auth(f):
    """ተጠቃሚው ከቴሌግራም መሆኑን የሚያረጋግጥ ዴኮሬተር (Decorator)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        init_data = request.headers.get("X-Telegram-Init-Data") or (request.json.get("initData") if request.is_json else None)
        
        if not init_data:
            return jsonify({"error": "Unauthorized: No Telegram Init Data provided"}), 401
            
        if not verify_telegram_init_data(init_data, BOT_TOKEN):
            return jsonify({"error": "Unauthorized: Invalid Telegram authentication"}), 401
            
        return f(*args, **kwargs)
    return decorated_function

def process_transaction(user_id, tx_type, amount, bonus_add=0.0):
    user_ref = db.collection("users").document(str(user_id))

    @firestore.transactional
    def _apply(transaction):
        user_doc = user_ref.get(transaction=transaction)
        if not user_doc.exists:
            return None
        user_data = user_doc.to_dict() or {}
        current_balance = user_data.get('balance', 0.0)
        bonus_part = float(user_data.get('bonus', 0) or 0)
        if tx_type == 'withdraw' and current_balance - amount < bonus_part - 1e-9:
            return None

        if tx_type == 'deposit' or tx_type == 'refund':
            new_balance = current_balance + amount
        elif tx_type == 'withdraw':
            new_balance = current_balance - amount
        else:
            new_balance = current_balance

        transactions = user_data.get('transactions', [])
        transactions.append({
            "type": tx_type,
            "amount": amount,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
        extra = {}
        if tx_type == 'deposit' and bonus_add > 0:
            new_balance += bonus_add
            extra["bonus"] = round(bonus_part + bonus_add, 2)
            transactions.append({"type": "deposit_bonus", "amount": bonus_add, "timestamp": datetime.utcnow().isoformat() + "Z"})
            user_data['bonus'] = extra["bonus"]
        transaction.update(user_ref, {"balance": new_balance, "transactions": transactions, **extra})

        user_data['balance'] = new_balance
        user_data['transactions'] = transactions
        return user_data

    result = _apply(db.transaction())
    if result:
        try:
            wallet.cache_set(user_id, float(result.get('balance', 0)), float(result.get('bonus', 0) or 0))
        except Exception:
            pass
    return result

print("✅ Successfully connected to Firebase Database!")

REFERRAL_BONUS = 10.0  
NEW_USER_BONUS = 5.0  
WITHDRAW_REQUIRES_DEPOSIT = os.environ.get("WITHDRAW_REQUIRES_DEPOSIT", "1") == "1"

def get_bonus_amounts():
    try:
        d = db.collection("settings").document("bonus").get().to_dict() or {}
        return float(d.get("referrer", REFERRAL_BONUS)), float(d.get("newcomer", NEW_USER_BONUS))
    except Exception:
        return REFERRAL_BONUS, NEW_USER_BONUS

def _apply_referral(new_user_id, inviter_bonus, newcomer_bonus):
    new_ref = db.collection("users").document(str(new_user_id))

    @firestore.transactional
    def run(txn):
        new_snap = new_ref.get(transaction=txn)
        new_data = (new_snap.to_dict() or {}) if new_snap.exists else {}
        referrer_id = new_data.get("referred_by")
        if not referrer_id or new_data.get("referral_bonus_paid") or str(referrer_id) == str(new_user_id):
            return None
        referrer_ref = db.collection("users").document(str(referrer_id))
        referrer_snap = referrer_ref.get(transaction=txn)
        if not referrer_snap.exists:
            return None
        stamp = datetime.utcnow().isoformat() + "Z"

        new_update = {"referral_bonus_paid": True}
        if newcomer_bonus > 0:
            new_update["balance"] = firestore.Increment(newcomer_bonus)
            new_update["bonus"] = firestore.Increment(newcomer_bonus)
            new_update["transactions"] = firestore.ArrayUnion([
                {"type": "bonus", "amount": newcomer_bonus, "timestamp": stamp, "note": "referral_welcome"}
            ])
        inviter_update = {"referrals_count": firestore.Increment(1)}
        if inviter_bonus > 0:
            inviter_update["balance"] = firestore.Increment(inviter_bonus)
            inviter_update["bonus"] = firestore.Increment(inviter_bonus)
            inviter_update["referral_earnings"] = firestore.Increment(inviter_bonus)
            inviter_update["transactions"] = firestore.ArrayUnion([
                {"type": "bonus", "amount": inviter_bonus, "timestamp": stamp, "note": "referral_invite"}
            ])
        txn.update(new_ref, new_update)
        txn.update(referrer_ref, inviter_update)
        return str(referrer_id)

    return run(db.transaction())

def maybe_pay_referral(new_user_id, phone_number):
    try:
        new_ref = db.collection("users").document(str(new_user_id))
        data = new_ref.get().to_dict() or {}
        if not data.get("referred_by") or data.get("referral_bonus_paid") or data.get("referral_blocked"):
            return
        others = [d.id for d in db.collection("users").where("phone_number", "==", phone_number).limit(3).stream()
                  if d.id != str(new_user_id)]
        if others:
            new_ref.set({"referral_blocked": "duplicate_phone"}, merge=True)
            bot.send_message(ADMIN_ID, f"⚠️ Referral bonus skipped for {new_user_id}: phone {phone_number} already used.")
            return
        inviter_bonus, newcomer_bonus = get_bonus_amounts()
        referrer_id = _apply_referral(new_user_id, inviter_bonus, newcomer_bonus)
        if not referrer_id:
            return
        try:
            wallet.cache_drop(new_user_id)
            wallet.cache_drop(referrer_id)
        except Exception:
            pass
        name = data.get("first_name") or "ጓደኛዎ"
        notes = []
        if newcomer_bonus > 0:
            notes.append((new_user_id, f"🎁 እንኳን ደስ አለዎት! በጓደኛዎ ግብዣ {newcomer_bonus:g} ETB ቦነስ ተጨምሯል።"))
        invited_text = f"🎉 {name} በእርስዎ ሊንክ ተቀላቅሏል!"
        if inviter_bonus > 0:
            invited_text += f" {inviter_bonus:g} ETB ቦነስ ተጨምሯል።"
        notes.append((referrer_id, invited_text))
        for chat_id, text in notes:
            try:
                bot.send_message(int(chat_id), text)
            except Exception:
                pass
    except Exception as e:
        print(f"referral error: {e}")

# ==========================================
# 🚀 SINGLE /START COMMAND HANDLER
# ==========================================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.chat.id
    first_name = message.from_user.first_name
    username = message.from_user.username or ""

    user_ref = db.collection("users").document(str(user_id))
    user_doc = user_ref.get()
    args = message.text.split()

    if len(args) > 1:
        if args[1] == "deposit":
            deposit_step_1_method(message)
            return
        elif args[1] == "withdraw":
            withdraw_step_1_method(message)
            return

    user_data = user_doc.to_dict() if user_doc.exists else {}

    if not user_doc.exists:
        referred_by = None
        initial_balance = 0.0

        if len(args) > 1 and args[1].startswith("ref_"):
            try:
                referrer_id = int(args[1].replace("ref_", ""))
                if referrer_id != user_id:
                    referred_by = str(referrer_id)
            except ValueError:
                pass

        user_ref.set({
            "telegram_id": str(user_id),
            "first_name": first_name,
            "username": username,
            "balance": initial_balance,
            "referred_by": referred_by,
            "created_at": firestore.SERVER_TIMESTAMP
        })

    # ስልክ ቁጥር ከሌለ መጠየቅ
    if "phone_number" not in user_data:
        markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton("📱 Share Phone Number", request_contact=True))
        bot.send_message(
            message.chat.id,
            f"Hello {first_name}! Welcome to Bingo Bot.\n\nPlease tap the button below to share your phone number and complete registration:",
            reply_markup=markup
        )
        return

    # ስልክ ቁጥር ካለ ዋናውን ምናሌ እና የ WebApp ፕሌይ በተን መላክ
    main_menu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_account = types.KeyboardButton(text="💼 የኔ ሂሳብ (Account)")
    btn_refer = types.KeyboardButton(text="🎁 ጋብዝ እና አግኝ (Refer)")
    btn_deposit = types.KeyboardButton(text="📥 ገቢ (Deposit)")
    btn_withdraw = types.KeyboardButton(text="📤 ወጪ (Withdraw)")
    btn_help = types.KeyboardButton(text="🎧 እርዳታ ማዕከል (Help & Support)")
    main_menu.add(btn_account, btn_refer, btn_deposit, btn_withdraw, btn_help)

    bot.send_message(message.chat.id, f"Welcome back, {first_name}!", reply_markup=main_menu)

    inline_markup = types.InlineKeyboardMarkup()
    inline_markup.add(types.InlineKeyboardButton("🎮 Play Bingo", web_app=types.WebAppInfo(url=WEBAPP_URL)))
    bot.send_message(message.chat.id, "Tap below to play:", reply_markup=inline_markup)

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    if message.contact is not None:
        if message.contact.user_id != message.from_user.id:
            bot.send_message(message.chat.id, "⚠️ እባክዎን በታች ባለው ቁልፍ የራስዎን ስልክ ቁጥር ብቻ ያጋሩ።")
            return
        user_id = str(message.chat.id)
        phone_number = message.contact.phone_number

        if not phone_number.startswith("+"):
            phone_number = "+" + phone_number

        db.collection("users").document(user_id).set({"phone_number": phone_number}, merge=True)

        main_menu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        main_menu.add(
            types.KeyboardButton(text="💼 የኔ ሂሳብ (Account)"),
            types.KeyboardButton(text="🎁 ጋብዝ እና አግኝ (Refer)"),
            types.KeyboardButton(text="📥 ገቢ (Deposit)"),
            types.KeyboardButton(text="📤 ወጪ (Withdraw)"),
            types.KeyboardButton(text="🎧 እርዳታ ማዕከል (Help & Support)")
        )
        bot.send_message(message.chat.id, "✅ Phone number registered successfully!", reply_markup=main_menu)

        inline_markup = types.InlineKeyboardMarkup()
        inline_markup.add(types.InlineKeyboardButton("🎮 Play Bingo", web_app=types.WebAppInfo(url=WEBAPP_URL)))
        bot.send_message(message.chat.id, "Tap below to open the WebApp:", reply_markup=inline_markup)
        
        maybe_pay_referral(user_id, phone_number)

@bot.message_handler(func=lambda message: message.text == "💼 የኔ ሂሳብ (Account)")
def show_profile(message):
    user_name = message.from_user.first_name
    user_id = str(message.chat.id)
    user_doc = db.collection("users").document(user_id).get()
    
    play_balance, phone = 0.0, "አልተመዘገበም"
    if user_doc.exists:
        user_data = user_doc.to_dict()
        play_balance = float(user_data.get("bonus", 0.0) or 0.0)
        main_balance = float(user_data.get("balance", 0.0)) - play_balance
        phone = user_data.get("phone_number", "አልተመዘገበም")

    profile_msg = (
        "👤 *የእርስዎ ፕሮፋይል (Your Profile)*\n"
        "───────────────\n"
        f"🔹 *ስም (Name):* {user_name}\n"
        f"🔹 *ስልክ (Phone):* {phone}\n\n"
        f"💰 *የጨዋታ ሂሳብ (Play Balance):* {play_balance:.2f} ETB\n"
        f"🏦 *ዋና ሂሳብ (Main Balance):* {main_balance:.2f} ETB\n"
        "───────────────\n"
        "💡 *ወደ ጨዋታ ሂሳብዎ ብር ለመጨመር '📥 ገቢ (Deposit)' የሚለውን ይጫኑ::*"
    )
    bot.send_message(message.chat.id, profile_msg, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📥 ገቢ (Deposit)")
def deposit_step_1_method(message):
    bot.clear_step_handler_by_chat_id(message.chat.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("Telebirr 📱", callback_data="dep_telebirr"),
               types.InlineKeyboardButton("CBEBirr 🏦", callback_data="dep_cbebirr"))
    bot.send_message(message.chat.id, "💰 ሂሳብ ለመሙላት የሚጠቀሙበትን የክፍያ አማራጭ ይምረጡ፡-", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ['dep_telebirr', 'dep_cbebirr'])
def deposit_step_2_amount(call):
    method = "Telebirr" if call.data == "dep_telebirr" else "CBEBirr"
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, f"እባክዎ በ {method} ማስገባት የሚፈልጉትን የብር መጠን ያስገቡ\n*(አነስተኛ መጠን: 50 ETB)*", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_deposit_amount, method)

def process_deposit_amount(message, method):
    if message.text in ["💼 የኔ ሂሳብ (Account)", "📥 ገቢ (Deposit)", "📤 ወጪ (Withdraw)", "🎁 ጋብዝ እና አግኝ (Refer)", "🎧 እርዳታ ማዕከል (Help & Support)"]:
        bot.send_message(message.chat.id, "ሂደቱ ተቋርጧል።")
        return
    try:
        amount = float(message.text)
        if amount < 50:
            msg = bot.send_message(message.chat.id, "⚠️ ይቅርታ፣ ማስገባት የሚችሉት አነስተኛ መጠን **50 ETB** ነው።", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_deposit_amount, method)
        else:
            instructions = (
                f"መሙላት የፈለጉት መጠን: **{amount:g} ETB**\n\n"
                f"እባክዎ ከታች ወዳለው የ{method} አካውንት ብሩን ያስገቡ።\n"
                f"👤 ስም: **Esrale**\n"
                f"📱 አካውንት: **0949196145**\n\n"
                f"የላኩበትን ማረጋገጫ (SMS ወይም ስክሪንሾት) ይላኩልን፦"
            )
            msg = bot.send_message(message.chat.id, instructions, parse_mode="Markdown")
            bot.register_next_step_handler(msg, receive_payment_proof, method, amount)
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ የተሳሳተ ቁጥር! የብር መጠኑን በቁጥር ብቻ ያስገቡ:")
        bot.register_next_step_handler(msg, process_deposit_amount, method)

RECEIVER_TOKENS = [t for t in os.environ.get("RECEIVER_NAME", "zeid fenta").lower().split() if t]
MENU_TEXTS = ["💼 የኔ ሂሳብ (Account)", "📥 ገቢ (Deposit)", "📤 ወጪ (Withdraw)", "🎁 ጋብዝ እና አግኝ (Refer)", "🎧 እርዳታ ማዕከል (Help & Support)"]

def receive_payment_proof(message, method, amount):
    user_id = message.chat.id
    if message.text and message.text in MENU_TEXTS:
        bot.send_message(user_id, "ሂደቱ ተሰርዟል።")
        return

    user_confirmation = "✅ የገቢ ጥያቄዎ ተልኳል! ክፍያው ከተረጋገጠ በኋላ ሂሳብዎ ይስተካከላል።"
    bot.send_message(user_id, user_confirmation)

    admin_msg = (
        "🚨 አዲስ የገቢ ጥያቄ (NEW DEPOSIT REQUEST)\n\n"
        f"👤 ተጠቃሚ: {message.from_user.first_name} (@{message.from_user.username or 'No Username'})\n"
        f"🆔 User ID: {user_id}\n"
        f"🏦 ባንክ: {method}\n"
        f"💵 መጠን: {amount} ETB\n"
        f"📝 ማስታወሻ: {message.text or message.caption or 'ፎቶ ብቻ'}"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ አፅድቅ (Approve)", callback_data=f"app_{user_id}_{amount}"),
               types.InlineKeyboardButton("❌ ውድቅ አድርግ (Reject)", callback_data=f"rej_{user_id}"))

    if message.photo:
        bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=admin_msg, reply_markup=markup)
    else:
        bot.send_message(ADMIN_ID, admin_msg, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('app_') or call.data.startswith('rej_'))
def handle_admin_decision(call):
    if call.message.chat.id != ADMIN_ID:
        return
    data = call.data.split('_')
    action, target_user_id = data[0], int(data[1])

    if action == "app":
        amount = float(data[2])
        updated_data = process_transaction(target_user_id, 'deposit', amount)
        new_total = updated_data.get('balance', 0.0) - float(updated_data.get('bonus', 0) or 0)
        bot.send_message(target_user_id, f"✅ የ {amount} ETB ገቢዎ ጸድቋል! አጠቃላይ ሂሳብዎ: **{new_total} ETB** ሆኗል::", parse_mode="Markdown")
        new_text = (call.message.caption or call.message.text) + "\n\n✅ **(APPROVED)**"
    else:
        bot.send_message(target_user_id, "❌ የገቢ ጥያቄዎ ውድቅ ተደርጓል።")
        new_text = (call.message.caption or call.message.text) + "\n\n❌ **(REJECTED)**"

    if call.message.photo:
        bot.edit_message_caption(caption=new_text, chat_id=ADMIN_ID, message_id=call.message.message_id, parse_mode="Markdown")
    else:
        bot.edit_message_text(text=new_text, chat_id=ADMIN_ID, message_id=call.message.message_id, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📤 ወጪ (Withdraw)")
def withdraw_step_1_method(message):
    bot.clear_step_handler_by_chat_id(message.chat.id)
    user_id = str(message.chat.id)
    user_doc = db.collection("users").document(user_id).get()
    
    balance = 0.0
    if user_doc.exists:
        balance = float(user_doc.to_dict().get("balance", 0.0)) - float(user_doc.to_dict().get("bonus", 0.0) or 0.0)

    if balance < 100:
        bot.send_message(message.chat.id, f"⚠️ አነስተኛው የወጪ መጠን **100 ETB** ነው። ያለዎት: **{balance:.2f} ETB**", parse_mode="Markdown")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("Telebirr 📱", callback_data="wit_telebirr"),
               types.InlineKeyboardButton("CBEBirr 🏦", callback_data="wit_cbebirr"))
    bot.send_message(message.chat.id, f"ያለዎት ሂሳብ: **{balance:.2f} ETB**\n\nባንክ ይምረጡ:-", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data in ['wit_telebirr', 'wit_cbebirr'])
def withdraw_step_2_amount(call):
    method = "Telebirr" if call.data == "wit_telebirr" else "CBEBirr"
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, f"በ {method} ማውጣት የሚፈልጉትን መጠን ያስገቡ (አነስተኛው 100 ETB):", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_withdraw_amount, method)

def process_withdraw_amount(message, method):
    try:
        amount = float(message.text)
        if amount < 100:
            msg = bot.send_message(message.chat.id, "⚠️ አነስተኛው 100 ETB ነው። እንደገና ያስገቡ:")
            bot.register_next_step_handler(msg, process_withdraw_amount, method)
        else:
            msg = bot.send_message(message.chat.id, f"የ {method} አካውንት ቁጥርዎን ያስገቡ:")
            bot.register_next_step_handler(msg, receive_withdraw_account, method, amount)
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ ትክክለኛ ቁጥር ያስገቡ:")
        bot.register_next_step_handler(msg, process_withdraw_amount, method)

def receive_withdraw_account(message, method, amount):
    account_info = message.text.strip()
    msg = bot.send_message(message.chat.id, "👤 የአካውንቱን ሙሉ ስም (Full Name) ያስገቡ:")
    bot.register_next_step_handler(msg, receive_withdraw_fullname, method, amount, account_info)

def receive_withdraw_fullname(message, method, amount, account_info):
    full_name = message.text.strip()
    user_id = str(message.chat.id)
    updated_data = process_transaction(user_id, 'withdraw', amount)
    if not updated_data:
        bot.send_message(message.chat.id, "⚠️ በቂ ሂሳብ የለዎትም ወይም ስህተት ተፈጥሯል።")
        return
    
    bot.send_message(message.chat.id, f"✅ የ {amount:g} ETB የወጪ ጥያቄዎ ተልኳል!")
    admin_msg = f"💸 አዲስ የወጪ ጥያቄ\nID: {user_id}\nባንክ: {method}\nመጠን: {amount} ETB\nአካውንት: {account_info}\nስም: {full_name}"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ አፅድቅ", callback_data=f"wapp_{user_id}_{amount}"),
               types.InlineKeyboardButton("❌ ውድቅ አድርግ", callback_data=f"wrej_{user_id}_{amount}"))
    bot.send_message(ADMIN_ID, admin_msg, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('wapp_') or call.data.startswith('wrej_'))
def handle_withdraw_admin_decision(call):
    if call.message.chat.id != ADMIN_ID:
        return
    data = call.data.split('_')
    action, target_user_id, amount = data[0], data[1], float(data[2])

    if action == "wapp":
        bot.send_message(target_user_id, f"✅ የ {amount:g} ETB የወጪ ጥያቄዎ ጸድቋል!")
        bot.edit_message_text(f"{call.message.text}\n\n✅ **APPROVED**", ADMIN_ID, call.message.message_id)
    else:
        user_ref = db.collection("users").document(str(target_user_id))
        doc = user_ref.get()
        if doc.exists:
            user_ref.update({"balance": doc.to_dict().get('balance', 0.0) + amount})
        bot.send_message(target_user_id, f"❌ የወጪ ጥያቄዎ ውድቅ ተደርጓል፣ ብሩ ተመልሷል።")
        bot.edit_message_text(f"{call.message.text}\n\n❌ **REJECTED & REFUNDED**", ADMIN_ID, call.message.message_id)

@bot.message_handler(func=lambda message: message.text == "🎁 ጋብዝ እና አግኝ (Refer)")
def show_referral_info(message):
    user_id = message.chat.id
    bot_username = bot.get_me().username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    bot.send_message(user_id, f"🎁 የጋበዣ ሊንክዎ:\n`{ref_link}`", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text and 'እርዳታ ማዕከል' in message.text)
def handle_help_support(message):
    bot.send_message(message.chat.id, "🎧 እርዳታ ለማግኘት ያነጋግሩን:\n📩 @zeid369", parse_mode="Markdown")

# --- FLASK APP & API ---
app = Flask(__name__)
CORS(app, origins=[WEBAPP_ORIGIN], allow_headers=["Content-Type", "X-Telegram-Init-Data"], max_age=7200)

wallet = FirestoreWallet()
engine = GameEngine(wallet, min_players=int(os.environ.get("MIN_PLAYERS", "2")))

@app.route('/')
def serve_webapp():
    return send_file('index.html')

@app.route('/health')
def health():
    alive = engine._thread is not None and engine._thread.is_alive()
    return jsonify({"status": "ok" if alive else "engine_down"}), (200 if alive else 503)

@app.route('/api/round', methods=['GET'])
@require_telegram_auth
def api_round():
    return jsonify({"status": "success", "state": engine.get_state(g.tg_user_id)}), 200

@app.route('/api/user-data', methods=['GET'])
@require_telegram_auth
def get_user_data():
    user_id = g.tg_user_id
    try:
        user_doc = db.collection('users').document(user_id).get()
        data = user_doc.to_dict() if user_doc.exists else {}
        return jsonify({
            "status": "success",
            "balance": data.get("balance", 0),
            "bonus": data.get("bonus", 0),
            "transactions": data.get("transactions", []),
            "phone_number": data.get("phone_number"),
            "first_name": data.get("first_name"),
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": "Server error"}), 500

def run_flask_server():
    port = int(os.environ.get("PORT", 5500))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    print("🤖 1X Bingo Bot is starting...")
    engine.start()
    Thread(target=run_flask_server, daemon=True).start()
    print("🌐 WebApp API running!")
    print("Bot is now running! Press Ctrl+C to stop.")
    bot.infinity_polling()
