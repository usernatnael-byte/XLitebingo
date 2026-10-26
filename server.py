import os
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# REPLACE WITH YOUR BOT TOKEN AND ADMIN TELEGRAM ID
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "YOUR_ADMIN_CHAT_ID_HERE")

# Mock In-Memory Databases (Replace or bind to your SQLite/MongoDB/Redis)
users_db = {}           # user_id -> {"balance": 0.0, "bonus": 0.0, ...}
pending_deposits = []   # list of deposit dicts
pending_withdraws = []  # list of withdraw dicts
game_counter = 42

# Helper function to send Telegram Messages via Bot API
def send_telegram_msg(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

# 1. GET PENDING DEPOSITS & WITHDRAWALS FOR ADMIN DASHBOARD
@app.route('/api/admin/pending-requests', methods=['GET'])
def get_pending_requests():
    return jsonify({
        "status": "success",
        "deposits": pending_deposits,
        "withdraws": pending_withdraws,
        "totalUsers": len(users_db),
        "totalGames": game_counter
    })

# 2. APPROVE DEPOSIT REQUEST
@app.route('/api/admin/approve-deposit', methods=['POST'])
def approve_deposit():
    data = request.json or {}
    req_id = data.get('reqId')
    user_id = str(data.get('userId'))
    amount = float(data.get('amount', 0))

    # Add to user play balance (bonus / deposit)
    if user_id in users_db:
        users_db[user_id]['bonus'] = users_db[user_id].get('bonus', 0.0) + amount
        users_db[user_id]['balance'] = users_db[user_id].get('balance', 0.0) + amount

    # Remove from pending list
    global pending_deposits
    pending_deposits = [d for d in pending_deposits if str(d.get('id')) != str(req_id)]

    # Notify player via Telegram
    send_telegram_msg(user_id, f"✅ *ዴፖዚትዎ ተጸድቋል!*\n\n{amount:.2f} ETB ወደ Play Walletዎ ገቢ ሆኗል:: አሁኑኑ ተመልሰው ይጫወቱ!")

    return jsonify({"status": "success", "message": "Deposit approved"})

# 3. REJECT DEPOSIT REQUEST
@app.route('/api/admin/reject-deposit', methods=['POST'])
def reject_deposit():
    data = request.json or {}
    req_id = data.get('reqId')

    global pending_deposits
    pending_deposits = [d for d in pending_deposits if str(d.get('id')) != str(req_id)]

    return jsonify({"status": "success", "message": "Deposit rejected"})

# 4. APPROVE WITHDRAWAL REQUEST
@app.route('/api/admin/approve-withdraw', methods=['POST'])
def approve_withdraw():
    data = request.json or {}
    req_id = data.get('reqId')
    user_id = str(data.get('userId'))
    amount = float(data.get('amount', 0))

    global pending_withdraws
    pending_withdraws = [w for w in pending_withdraws if str(w.get('id')) != str(req_id)]

    # Notify player
    send_telegram_msg(user_id, f"🎉 *የገንዘብ ማውጣት ጥያቄዎ ተጸድቋል!*\n\n{amount:.2f} ETB ወደ ሂሳብዎ ተልኳል:: አመሰግናለሁ!")

    return jsonify({"status": "success", "message": "Withdrawal approved"})

# 5. REJECT WITHDRAWAL REQUEST (REFUND)
@app.route('/api/admin/reject-withdraw', methods=['POST'])
def reject_withdraw():
    data = request.json or {}
    req_id = data.get('reqId')
    user_id = str(data.get('userId'))
    amount = float(data.get('amount', 0))

    # Refund back to user main balance
    if user_id in users_db:
        users_db[user_id]['balance'] = users_db[user_id].get('balance', 0.0) + amount

    global pending_withdraws
    pending_withdraws = [w for w in pending_withdraws if str(w.get('id')) != str(req_id)]

    send_telegram_msg(user_id, f"⚠️ *የገንዘብ ማውጣት ጥያቄዎ አልተሳካም*\n\n{amount:.2f} ETB ወደ Main Walletዎ ተመልሷል::")

    return jsonify({"status": "success", "message": "Withdrawal rejected & refunded"})

# 6. MANUAL BALANCE ADJUSTMENT (ADD / SUBTRACT)
@app.route('/api/admin/adjust-balance', methods=['POST'])
def adjust_balance():
    data = request.json or {}
    user_id = str(data.get('userId'))
    amount = float(data.get('amount', 0))
    wallet_type = data.get('walletType', 'play')

    if user_id not in users_db:
        users_db[user_id] = {'balance': 0.0, 'bonus': 0.0}

    if wallet_type == 'play':
        users_db[user_id]['bonus'] = max(0.0, users_db[user_id].get('bonus', 0.0) + amount)
        users_db[user_id]['balance'] = max(0.0, users_db[user_id].get('balance', 0.0) + amount)
    else:
        users_db[user_id]['balance'] = max(0.0, users_db[user_id].get('balance', 0.0) + amount)

    action_word = "ተጨምሯል" if amount > 0 else "ቀንሷል"
    send_telegram_msg(user_id, f"🔔 *የሂሳብ ማስተካከያ*\n\nየእርስዎ {wallet_type.upper()} WALLET በ {abs(amount):.2f} ETB {action_word}::")

    return jsonify({"status": "success", "new_balance": users_db[user_id]['balance']})

# 7. BROADCAST MESSAGE TO ALL USERS
@app.route('/api/admin/broadcast', methods=['POST'])
def broadcast_message():
    data = request.json or {}
    msg_text = data.get('message', '').strip()

    if not msg_text:
        return jsonify({"status": "error", "message": "Empty message"}), 400

    # Send to all registered user IDs
    count = 0
    for uid in users_db.keys():
        send_telegram_msg(uid, f"📢 *ከአድሚን የተላከ ማስታወቂያ*\n\n{msg_text}")
        count += 1

    return jsonify({"status": "success", "sent_count": count})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
