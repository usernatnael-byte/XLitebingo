import os
import logging
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import firebase_admin
from firebase_admin import credentials, firestore

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask App setup
app = Flask(__name__)

# Telegram Bot Token from Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

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

# Flask Routes (Health check & WebApp APIs)
@app.route('/')
def index():
    return "1X Bingo Bot & WebApp API is running!", 200

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
    return jsonify({"balance": 0, "username": "Player"}), 200

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    return jsonify([]), 200

# Telegram Handlers
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    # Save or check user in Firestore 'default' database
    if db:
        try:
            user_ref = db.collection('users').document(str(user_id))
            user_doc = user_ref.get()
            if not user_doc.exists:
                user_ref.set({
                    'user_id': user_id,
                    'username': username,
                    'balance': 0,
                    'created_at': firestore.SERVER_TIMESTAMP
                })
        except Exception as e:
            logger.error(f"Error saving user in start command: {e}")

    # Create Interactive Markup Buttons
    markup = InlineKeyboardMarkup()
    web_app_url = "https://xlitebingo.onrender.com"  # Your primary Render URL
    
    markup.add(InlineKeyboardButton("🎮 Play Bingo", web_app=WebAppInfo(url=web_app_url)))
    markup.add(InlineKeyboardButton("💰 Balance & Profile", callback_data="profile"),
               InlineKeyboardButton("👥 Invite Friends", callback_data="invite"))
    markup.add(InlineKeyboardButton("ℹ️ Help & Rules", callback_data="help"))

    welcome_text = (
        f"👋 Welcome to **1X Bingo**, {username}!\n\n"
        "Get ready to play exciting live bingo games, win rewards, and compete with friends.\n\n"
        "Click the button below to launch the game!"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.data == "profile":
        bot.answer_callback_query(call.id, "Loading profile...")
        bot.send_message(call.message.chat.id, "💰 Your current balance: 0 ETB")
    elif call.data == "invite":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "👥 Share your referral link with friends to earn bonuses!")
    elif call.data == "help":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "ℹ️ Rules: Join a room, match numbers on your card, and shout BINGO!")

if __name__ == '__main__':
    import threading
    
    # Run Telegram bot polling in a background thread
    def run_bot():
        try:
            logger.info("🤖 1X Bingo Bot is starting polling...")
            bot.infinity_polling(skip_pending=True)
        except Exception as e:
            logger.error(f"Bot polling error: {e}")

    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Run Flask web server
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
