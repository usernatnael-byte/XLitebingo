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
import urllib.parse
import time
import logging
import json
from urllib.parse import urlparse
from game_engine import GameEngine, TICKET_PRICE, PRIZE_PER_CARTEL, MAX_SELECTION
from wallet_firestore import FirestoreWallet
from collections import defaultdict, deque
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Firebase Initialization
if not firebase_admin._apps:
    cred_path = os.getenv("FIREBASE_CREDENTIALS", "firebase_key.json")
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    else:
        firebase_admin.initialize_app()

# Explicitly connect to the 'default' Firestore database to fix 404 errors
try:
    db = firestore.client(database_id='default')
    logger.info("Firebase initialized successfully with 'default' database.")
except Exception as e:
    logger.error(f"Firestore initialization error: {e}")
    db = None


# Initialize Firebase Connection (Checking standard Render secret file mount paths)
cred_path = os.environ.get("FIREBASE_KEY_PATH", "firebase_key.json")
if not os.path.exists(cred_path) and os.path.exists("/etc/secrets/firebase_key.json"):
    cred_path = "/etc/secrets/firebase_key.json"

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase initialized successfully.")
    except Exception as e:
        logger.error(f"Firebase initialization error: {e}")

db = firestore.client() if firebase_admin._apps else None

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

# Configuration Constants
TOKEN = os.environ.get("BOT_TOKEN", "8747562686:AAGQCIOwD3ahfjVY21PY4gvftQCtxaq0UNA")  
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://xlitebingo.onrender.com")  
_u = urlparse(WEBAPP_URL)
WEBAPP_ORIGIN = f"{_u.scheme}://{_u.netloc}"
RESET_TOKEN = os.environ.get("RESET_TOKEN", "MySuperSecretBingoTokenN2026")  

bot = telebot.TeleBot(TOKEN)
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7396414604"))

CANCEL_BUTTONS = [
    "💼 የኔ ሂሳብ (Account)",
    "📥 ገቢ (Deposit)",
    "📤 ወጪ (Withdraw)",
    "🎁 ጋብዝ እና አግኝ (Refer)",
    "🎧 እርዳታ ማዕከል (Help & Support)"
]

# Robust Telegram WebApp Authentication Decorator with Fallback for Testing
def require_telegram_auth(f):
    def decorated(*args, **kwargs):
        # Allow testing via query parameter ?userId=test_user if needed
        test_user = request.args.get('userId')
        if test_user:
            g.tg_user_id = str(test_user)
            return f(*args, **kwargs)

        auth_header = request.headers.get('X-Telegram-Init-Data', '')
        if not auth_header:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        try:
            parsed = urllib.parse.parse_qsl(auth_header, keep_blank_values=True)
            data_check_string = sorted([f"{k}={v}" for k, v in parsed if k != 'hash'])
            data_check_string = "\n".join(data_check_string)
            
            hash_val = dict(parsed).get('hash', '')
            secret_key = hashlib.sha256(TOKEN.encode()).digest()
            calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
            
            if not hmac.compare_digest(calculated_hash, hash_val):
                return jsonify({"status": "error", "message": "Invalid auth signature"}), 401
                
            user_data_str = dict(parsed).get('user', '{}')
            user_json = json.loads(user_data_str) if isinstance(user_data_str, str) else {}
            g.tg_user_id = str(user_json.get('id', ''))
            if not g.tg_user_id:
                return jsonify({"status": "error", "message": "User ID missing"}), 401
        except Exception as e:
            logger.error(f"Auth validation error: {e}")
            return jsonify({"status": "error", "message": "Authentication failed"}), 401
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated

def get_main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_account = types.KeyboardButton(text="💼 የኔ ሂሳብ (Account)")
    btn_refer = types.KeyboardButton(text="🎁 ጋብዝ እና አግኝ (Refer)")
    btn_deposit = types.KeyboardButton(text="📥 ገቢ (Deposit)")
    btn_withdraw = types.KeyboardButton(text="📤 ወጪ (Withdraw)")
    btn_help = types.KeyboardButton(text="🎧 እርዳታ ማዕከል (Help & Support)")

    markup.add(btn_account, btn_refer)
    markup.add(btn_deposit, btn_withdraw)
    markup.add(btn_help)
    return markup

REFERRAL_BONUS = 10.0  
NEW_USER_BONUS = 5.0  
WITHDRAW_REQUIRES_DEPOSIT = os.environ.get("WITHDRAW_REQUIRES_DEPOSIT", "1") == "1"

def withdraw_block_message(user_data):
    if not WITHDRAW_REQUIRES_DEPOSIT:
        return None
    txs = (user_data or {}).get("transactions") or []
    last_bonus = max((i for i, t in enumerate(txs) if t.get("type") == "bonus"), default=-1)
    if last_bonus >= 0 and not any(t.get("type") == "deposit" for t in txs[last_bonus + 1:]):
        return "⚠️ ቦነስ ካገኙ በኋላ ገንዘብ ከማውጣትዎ በፊት ቢያንስ አንድ ጊዜ ገቢ (Deposit) ማድረግ አለብዎት።"
    return None

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
            if ADMIN_ID:
                bot.send_message(ADMIN_ID, f"⚠️ Referral bonus skipped for {new_user_id}: phone {phone_number} "
                                           f"is already used by account {others[0]}.")
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
            notes.append((new_user_id, f"🎁 እንኳን ደስ አለዎት! በጓደኛዎ ግብዣ ስለተቀላቀሉ {newcomer_bonus:g} ETB ቦነስ ወደ ሂሳብዎ ተጨምሯል።"))
        invited_text = f"🎉 {name} በእርስዎ ሊንክ ተቀላቅሏል!"
        if inviter_bonus > 0:
            invited_text += f" {inviter_bonus:g} ETB ቦነስ ወደ ሂሳብዎ ተጨምሯል።"
        notes.append((referrer_id, invited_text))
        for chat_id, text in notes:
            try:
                bot.send_message(int(chat_id), text)
            except Exception:
                pass
    except Exception as e:
        print(f"referral error for {new_user_id}: {e}")

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

    if "phone_number" not in user_data:
        markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton("📱 Share Phone Number", request_contact=True))
        bot.send_message(
            message.chat.id,
            f"Hello {first_name}! Welcome to Bingo Bot.\n\nPlease tap the button below to share your phone number and complete registration:",
            reply_markup=markup
        )
        return

    main_menu = get_main_menu()
    bot.send_message(
        message.chat.id,
        f"Welcome back, {first_name}!",
        reply_markup=main_menu
    )

    inline_markup = types.InlineKeyboardMarkup()
    inline_markup.add(types.InlineKeyboardButton("🎮 Play Bingo", web_app=types.WebAppInfo(url=WEBAPP_URL)))
    bot.send_message(
        message.chat.id,
        "Tap below to play:",
        reply_markup=inline_markup
    )

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

        main_menu = get_main_menu()
        bot.send_message(
            message.chat.id,
            "✅ Phone number registered successfully!",
            reply_markup=main_menu
        )

        inline_markup = types.InlineKeyboardMarkup()
        inline_markup.add(types.InlineKeyboardButton("🎮 Play Bingo", web_app=types.WebAppInfo(url=WEBAPP_URL)))
        bot.send_message(
            message.chat.id,
            "Tap below to open the WebApp:",
            reply_markup=inline_markup
        )
        
        maybe_pay_referral(user_id, phone_number)

@bot.message_handler(func=lambda message: message.text == "💼 የኔ ሂሳብ (Account)")
def show_profile(message):
    user_name = message.from_user.first_name
    user_id = str(message.chat.id)

    user_doc = db.collection("users").document(user_id).get()
    play_balance = 0.0
    phone = "አልተመዘገበም"
    
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
        f"🏆 *የአሸናፊነት ሂሳብ (Win Balance):* 0.00 ETB\n"
        "───────────────\n"
        "💡 *ወደ ጨዋታ ሂሳብዎ ብር ለመጨመር '📥 ገቢ (Deposit)' የሚለውን ይጫኑ::*"
    )
    bot.send_message(message.chat.id, profile_msg, parse_mode="Markdown")

# ==========================================
# 📥 DEPOSIT BUTTON LOGIC (Multi-step)
# ==========================================
@bot.message_handler(func=lambda message: message.text == "📥 ገቢ (Deposit)")
def deposit_step_1_method(message):
    bot.clear_step_handler_by_chat_id(message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_telebirr = types.InlineKeyboardButton("Telebirr 📱", callback_data="dep_telebirr")
    btn_cbe = types.InlineKeyboardButton("CBEBirr 🏦", callback_data="dep_cbebirr")
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
    if message.text in CANCEL_BUTTONS:
        bot.send_message(message.chat.id, "ሂደቱ ተቋርጧል። (Process cancelled.)")
        return

    try:
        amount = float(message.text)
        if amount < 50:
            msg = bot.send_message(message.chat.id, "⚠️ ይቅርታ፣ ማስገባት የሚችሉት አነስተኛ መጠን **50 ETB** ነው።\nእባክዎ ትክክለኛ መጠን ያስገቡ፦", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_deposit_amount, method)
        else:
            instructions = (
                f"{deposit_offer_line(amount)}"
                f"መሙላት የፈለጉት መጠን: **{amount:g} ETB**\n\n"
                f"እባክዎ ከታች ወዳለው የ{method} አካውንት ብሩን ያስገቡ።\n"
                f"👤 ስም: **Zeid**\n"
                f"📱 አካውንት: **0935084226**\n\n"
                f"የላኩበትን ማረጋገጫ አንዱን ይላኩልን፦\n"
                f"1️⃣ ሚሴጅ (SMS)\n"
                f"2️⃣ የደረሰኝ ፎቶ (screenshot)\n"
            )
            msg = bot.send_message(message.chat.id, instructions, parse_mode="Markdown")
            bot.register_next_step_handler(msg, receive_payment_proof, method, amount)
            
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ የተሳሳተ ቁጥር! እባክዎ የብር መጠኑን በቁጥር ብቻ ያስገቡ (ለምሳሌ፦ 100)፡")
        bot.register_next_step_handler(msg, process_deposit_amount, method)

RECEIVER_TOKENS = [t for t in os.environ.get("RECEIVER_NAME", "zeid fenta").lower().split() if t]
INVALID_MSG = ("❌ Invalid. Please input the proper text message or screenshot (recommended).\n"
               "❌ ልክ አይደለም። እባክዎ ትክክለኛውን የክፍያ መልእክት (text) ወይም ስክሪንሾት (የሚመከር) ያስገቡ።")
WRONG_RECEIVER_MSG = "❌ ገንዘቡ ወደ ትክክለኛው አካውንት አልተላከም። (The money must be sent to the account shown above.)"
USED_MSG = "❌ ይህ ደረሰኝ ቀድሞ ጥቅም ላይ ውሏል። (This receipt was already used.)"

_TB = re.compile(r"you have transferred etb\s*([\d,]+(?:\.\d+)?)\s+to\s+(.+?)\s*\(([\d*]+)\)\s+on\s+\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\.?\s*your transaction number is\s+([a-z0-9]{8,14})", re.I)
_TB_LINK = re.compile(r"ethiotelecom\.et/receipt/([a-z0-9]+)", re.I)
_CBE = re.compile(r"you have successfully transferred etb\s*([\d,]+(?:\.\d+)?)\s+from account\s+(\S+)\s+to account\s+(\S+)\s*\((.+?)\)", re.I)
_CBE_BAL = re.compile(r"current balance is etb\s*([\d,]+(?:\.\d+)?)", re.I)
_CBE_LINK = re.compile(r"cbe\.com\.et/([A-Za-z0-9_-]+)")

def _clean_key(k):
    return re.sub(r"[^A-Za-z0-9_-]", "_", k)[:120]

def validate_receipt(text, method, declared_amount):
    t = " ".join((text or "").split())
    if method == "Telebirr":
        m = _TB.search(t)
        if not m:
            return False, "format"
        amount, receiver, code = float(m.group(1).replace(",", "")), m.group(2), m.group(4).upper()
        link = _TB_LINK.search(t)
        if link and link.group(1).upper() != code:
            return False, "format"
        key, ref = "tb_" + code, code
    else:
        m = _CBE.search(t)
        if not m:
            return False, "format"
        amount, receiver = float(m.group(1).replace(",", "")), m.group(4)
        link, bal = _CBE_LINK.search(t), _CBE_BAL.search(t)
        if link:
            key, ref = "cbe_" + link.group(1), link.group(1)
        elif bal:
            key, ref = f"cbe_{m.group(2)}_{amount:g}_{bal.group(1)}", f"{m.group(2)}/{bal.group(1)}"
        else:
            return False, "format"
    if not all(tok in receiver.lower() for tok in RECEIVER_TOKENS):
        return False, "receiver"
    if abs(amount - float(declared_amount)) > 0.01:
        return False, "amount"
    return True, {"amount": amount, "key": _clean_key(key), "ref": ref}

def _claim_receipt(key, user_id, amount, method):
    try:
        db.collection("receipts").document(key).create({
            "user_id": str(user_id), "amount": amount, "method": method, "status": "pending",
            "at": datetime.utcnow().isoformat() + "Z"})
        return True
    except Excepti
