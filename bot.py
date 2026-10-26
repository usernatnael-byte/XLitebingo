import os
import threading
import time
import logging
import hmac
import hashlib
import urllib.parse
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
import telebot
import firebase_admin
from firebase_admin import credentials, firestore

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8747562686:AAGQCIOwD3ahfjVY21PY4gvftQCtxaq0UNA")
MIN_PLAYERS = int(os.environ.get("MIN_PLAYERS", 1))
RESET_TOKEN = os.environ.get("RESET_TOKEN", "MySuperSecretBingoTokenN2026")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://your-app.onrender.com")

# Initialize Firebase
cred_path = os.environ.get("FIREBASE_KEY_PATH", "firebase_key.json")
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase initialized successfully.")
    except Exception as e:
        logger.error(f"Firebase initialization error: {e}")

db = firestore.client() if firebase_admin._apps else None

# Initialize Telegram Bot
bot = telebot.TeleBot(BOT_TOKEN)

# Initialize Flask App
app = Flask(__name__)
CORS(app)

# Telegram Auth Validator (Built-in to avoid missing module errors)
def validate_telegram_init_data(init_data, bot_token):
    try:
        parsed = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
        data_check_string = sorted([f"{k}={v}" for k, v in parsed if k != 'hash'])
        data_check_string = "\n".join(data_check_string)
        
        hash_val = dict(parsed).get('hash', '')
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        return hmac.compare_digest(calculated_hash, hash_val)
    except Exception as e:
        logger.error(f"Auth validation error: {e}")
        return False

# Telegram Bot Handlers
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = telebot.types.InlineKeyboardMarkup()
    web_app_btn = telebot.types.InlineKeyboardButton(
        text="🎮 Play 1xBingo",
        web_app=telebot.types.WebAppInfo(url=WEBAPP_URL)
    )
    markup.add(web_app_btn)
    bot.reply_to(message, "እንኳን ደህና መጡ! ወደ 1xBingo ጨዋታ በደህና መጡ። ጨዋታውን ለመጀመር ከታች ያለውን ቁልፍ ይጫኑ።", reply_markup=markup)

# Flask Routes
@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "running", "message": "1xBingo Backend & Bot Server is active!"})

@app.route("/api/reset-weekly", methods=["POST"])
def reset_weekly():
    token = request.headers.get("X-Reset-Token")
    if token != RESET_TOKEN:
        return jsonify({"error": "Unauthorized"}), 403
    
    try:
        # Weekly leaderboard reset logic can be placed here
        return jsonify({"success": True, "message": "Weekly leaderboard reset successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    # Start Flask in a background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask server started in background thread.")

    # Start Telegram Bot polling in main thread
    logger.info("Starting Telegram Bot polling...")
    bot.infinity_polling(skip_pending=True)
