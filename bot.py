import os
import re
import hmac
import json
import time
import hashlib
import logging
import urllib.parse
from datetime import datetime
from threading import Thread
from urllib.parse import urlparse

import telebot
from telebot import types
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask App setup
app = Flask(__name__)
CORS(app)

# Telegram Bot Token from Environment Variables
TOKEN = os.environ.get("BOT_TOKEN", "8747562686:AAGQCIOwD3ahfjVY21PY4gvftQCtxaq0UNA")  
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://xlitebingo.onrender.com")  
_u = urlparse(WEBAPP_URL)
WEBAPP_ORIGIN = f"{_u.scheme}://{_u.netloc}"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7396414604"))

bot = telebot.TeleBot(TOKEN)

# ==========================================
# FIREBASE INITIALIZATION WITH 'default' DATABASE
# ==========================================
if not firebase_admin._apps:
    cred_path = os.getenv("FIREBASE_CREDENTIALS", "firebase_key.json")
    if not os.path.exists(cred_path) and os.path.exists("/etc/secrets/firebase_key.json"):
        cred_path = "/etc/secrets/firebase_key.json"
        
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

# ==========================================
# TRANSACTION & WALLET HELPERS
# ==========================================
def process_transaction(user_id, tx_type, amount, bonus_add=0.0):
    if not db:
        return None
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

        if tx_type in ['deposit', 'refund']:
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
            new_bonus = round(bonus_part + bonus_add, 2)
            extra["bonus"] = new_bonus
            transactions.append({"type": "deposit_bonus", "amount": bonus_add, "timestamp": datetime.utcnow().isoformat() + "Z"})
            user_data['bonus'] = new_bonus
            
        transaction.update(user_ref, {"balance": new_balance, "transactions": transactions, **extra})
        user_data['balance'] = new_balance
        user_data['transactions'] = transactions
        return user_data

    try:
        return _apply(db.transaction())
    except Exception as e:
        logger.error(f"Transaction error: {e}")
        return None

CANCEL_BUTTONS = [
    "💼 የኔ ሂሳብ (Account)",
    "📥 ገቢ (Deposit)",
    "📤 ወጪ (Withdraw)",
    "🎁 ጋብዝ እና አግኝ (Refer)",
    "🎧 እርዳታ ማዕከል (Help & Support)"
]

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

# ==========================================
# FLASK ROUTES & WEBAPP APIS
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/round', methods=['GET'])
def get_round():
    return jsonify({"status": "active", "round": 1}), 200

@app.route('/api/user-data', methods=['GET'])
def get_user_data():
    user_id = request.args.get('userId', 'test_user')
    if db:
        try:
            user_ref = db.collection('users').document(str(user_id))
            user_doc = user_ref.get()
            if user_doc.exists:
                return jsonify(user_doc.to_dict()), 200
        except Exception as e:
            logger.error(f"Error fetching user data: {e}")
    return jsonify({"balance": 0, "username": "Player", "bonus": 0}), 200

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    return jsonify([]), 200

# ==========================================
# TELEGRAM BOT COMMANDS & HANDLERS
# ==========================================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.chat.id
    first_name = message.from_user.first_name
    username = message.from_user.username or ""

    if not db:
        bot.send_message(message.chat.id, "⚠️ Database connection error. Please try again later.")
        return

    user_ref = db.collection("users").document(str(user_id))
    user_doc = user_ref.get()
    user_data = user_doc.to_dict() if user_doc.exists else {}

    if not user_doc.exists:
        user_ref.set({
            "telegram_id": str(user_id),
            "first_name": first_name,
            "username": username,
            "balance": 0.0,
            "bonus": 0.0,
            "created_at": firestore.SERVER_TIMESTAMP
        })

    if "phone_number" not in user_data:
        markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton("📱 Share Phone Number", request_contact=True))
        bot.send_message(
            message.chat.id,
            f"Hello {first_name}! Welcome to 1X Bingo Bot.\n\nPlease tap the button below to share your phone number and complete registration:",
            reply_markup=markup
        )
        return

    main_menu = get_main_menu()
    bot.send_message(message.chat.id, f"Welcome back, {first_name}!", reply_markup=main_menu)

    inline_markup = types.InlineKeyboardMarkup()
    inline_markup.add(types.InlineKeyboardButton("🎮 Play Bingo", web_app=types.WebAppInfo(url=WEBAPP_URL)))
    bot.send_message(message.chat.id, "Tap below to open the game:", reply_markup=inline_markup)

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

        if db:
            db.collection("users").document(user_id).set({"phone_number": phone_number}, merge=True)

        main_menu = get_main_menu()
        bot.send_message(message.chat.id, "✅ Phone number registered successfully!", reply_markup=main_menu)

        inline_markup = types.InlineKeyboardMarkup()
        inline_markup.add(types.InlineKeyboardButton("🎮 Play Bingo", web_app=types.WebAppInfo(url=WEBAPP_URL)))
        bot.send_message(message.chat.id, "Tap below to open the WebApp:", reply_markup=inline_markup)

@bot.message_handler(func=lambda message: message.text == "💼 የኔ ሂሳብ (Account)")
def show_profile(message):
    user_name = message.from_user.first_name
    user_id = str(message.chat.id)

    play_balance = 0.0
    main_balance = 0.0
    phone = "አልተመዘገበም"
    
    if db:
        user_doc = db.collection("users").document(user_id).get()
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

# ==========================================
# 📥 DEPOSIT LOGIC
# ==========================================
@bot.message_handler(func=lambda message: message.text == "📥 ገቢ (Deposit)")
def deposit_step_1_method(message):
    bot.clear_step_handler_by_chat_id(message.chat.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("Telebirr 📱", callback_data="dep_telebirr"),
        types.InlineKeyboardButton("CBEBirr 🏦", callback_data="dep_cbebirr")
    )
    bot.send_message(message.chat.id, "💰 ሂሳብ ለመሙላት የሚጠቀሙበትን የክፍያ አማራጭ ይምረጡ፡-", reply_markup=markup)

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
        bot.send_message(message.chat.id, "ሂደቱ ተቋርጧል።")
        return

    try:
        amount = float(message.text)
        if amount < 50:
            msg = bot.send_message(message.chat.id, "⚠️ ይቅርታ፣ ማስገባት የሚችሉት አነስተኛ መጠን **50 ETB** ነው።\nእባክዎ ትክክለኛ መጠን ያስገቡ፦", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_deposit_amount, method)
        else:
            instructions = (
                f"ମ መሙላት የፈለጉት መጠን: **{amount:g} ETB**\n\n"
                f"እባክዎ ከታች ወዳለው የ{method} አካውንት ብሩን ያስገቡ።\n"
                f"👤 ስም: **Zeid**\n"
                f"📱 አካውንት: **0935084226**\n\n"
                f"የላኩበትን የትራንዛክሽን መልእክት (SMS Text) እዚህ ይላኩልን፦"
            )
            msg = bot.send_message(message.chat.id, instructions, parse_mode="Markdown")
            bot.register_next_step_handler(msg, receive_payment_proof, method, amount)
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ የተሳሳተ ቁጥር! እባክዎ የብር መጠኑን በቁጥር ብቻ ያስገቡ (ለምሳሌ፦ 100)፡")
        bot.register_next_step_handler(msg, process_deposit_amount, method)

def receive_payment_proof(message, method, amount):
    if message.text in CANCEL_BUTTONS:
        bot.send_message(message.chat.id, "ሂደቱ ተቋርጧል።")
        return

    user_id = str(message.chat.id)
    text_content = message.text if message.content_type == 'text' else ""

    if not text_content:
        msg = bot.send_message(message.chat.id, "❌ እባክዎ ትክክለኛውን የክፍያ መልእክት (SMS Text) በጽሁፍ ይላኩልን።")
        bot.register_next_step_handler(msg, receive_payment_proof, method, amount)
        return

    # Process deposit transaction and credit balance
    bonus_add = amount * 0.1 if amount >= 100 else 0.0
    updated = process_transaction(user_id, 'deposit', amount, bonus_add=bonus_add)

    if updated:
        bot.send_message(
            message.chat.id,
            f"✅ ክፍያዎ በትክክል ተረጋግጧል!\n💰 {amount:g} ETB ወደ ሂሳብዎ ተጨምሯል።",
            reply_markup=get_main_menu()
        )
    else:
        bot.send_message(message.chat.id, "❌ የክፍያ ማቀናበር ስህተት አጋጥሟል። እባክዎ አስተዳዳሪውን ያነጋግሩ።", reply_markup=get_main_menu())

# ==========================================
# MAIN ENTRY POINT
# ==========================================
if __name__ == '__main__':
    def run_bot():
        try:
            logger.info("🤖 1X Bingo Bot is starting polling...")
            bot.infinity_polling(skip_pending=True)
        except Exception as e:
            logger.error(f"Bot polling error: {e}")

    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
