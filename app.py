import os
import json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, db as rtdb
from game_engine import GameEngine

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# --- Firebase ማስጀመር ---
if not firebase_admin._apps:
    cred = None
    private_key = os.environ.get("FIREBASE_PRIVATE_KEY")
    client_email = os.environ.get("FIREBASE_CLIENT_EMAIL")
    project_id = os.environ.get("FIREBASE_PROJECT_ID")
    
    if private_key and client_email and project_id:
        private_key = private_key.replace('\\n', '\n')
        cred_dict = {
            "type": "service_account",
            "project_id": project_id,
            "private_key_id": "1a275129ef2d718611aaafa9f43093777b1659f7",
            "private_key": private_key,
            "client_email": client_email,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{client_email.replace('@', '%40')}"
        }
        try:
            cred = credentials.Certificate(cred_dict)
        except Exception as e:
            print(f"⚠️ Firebase Env Error: {e}")

    if not cred and os.path.exists("firebase_key.json"):
        try:
            cred = credentials.Certificate("firebase_key.json")
        except Exception as e:
            print(f"⚠️ Firebase JSON Error: {e}")

    if cred:
        try:
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://litebingo-513a9-default-rtdb.firebaseio.com/'
            })
            print("✅ Firebase Connected Successfully!")
        except Exception as e:
            print(f"⚠️ Firebase Init Error: {e}")
    else:
        print("⚠️ Continuing without DB credentials")


# --- ኪስ ቦርሳ (Wallet Class) ---
class RTDBWallet:
    def recover_unsettled(self):
        return 0

    def get_balance(self, uid):
        if uid == "bot_player":
            return 999999.0
        if not firebase_admin._apps:
            return 1000.0
        try:
            user_data = rtdb.reference(f"users/{uid}").get() or {}
            return float(user_data.get("balance", 1000.0))
        except Exception:
            return 1000.0

    def begin_round(self, rid, snapshot):
        pass

    def charge(self, uid, amount, rid, cartels=1):
        if uid == "bot_player":
            return 999999.0
        if not firebase_admin._apps:
            return 1000.0
        try:
            ref = rtdb.reference(f"users/{uid}")
            data = ref.get() or {}
            current = float(data.get("balance", 1000.0))
            if current < amount:
                return None
            new_balance = current - amount
            ref.update({"balance": new_balance})
            return new_balance
        except Exception:
            return 1000.0

    def refund(self, uid, rid):
        pass

    def start_drawing(self, rid, tickets):
        pass

    def settle(self, rid, payouts):
        if not firebase_admin._apps:
            return
        try:
            for uid, prize in payouts.items():
                if uid == "bot_player":
                    continue
                ref = rtdb.reference(f"users/{uid}")
                data = ref.get() or {}
                current = float(data.get("balance", 0.0))
                new_bal = current + prize
                total_win = float(data.get("total_winnings", 0.0)) + prize
                ref.update({"balance": new_bal, "total_winnings": total_win})
        except Exception as e:
            print(f"Settle error: {e}")

    def cancel_round(self, rid, uids):
        pass

    def profile(self, uid):
        if uid == "bot_player":
            return {"name": "Bingo Bot", "phone": "0911223344", "username": "bingo_bot"}
        if not firebase_admin._apps:
            return {}
        try:
            return rtdb.reference(f"users/{uid}").get() or {}
        except Exception:
            return {}


# --- ሞተርን ማስጀመር ---
wallet_instance = RTDBWallet()
engine = GameEngine(wallet=wallet_instance)
engine.start()


# --- የ Flask API ራውቶች (Routes) ---
@app.route('/')
def serve_index():
    base_dir = os.path.abspath(os.path.dirname(__file__))
    return send_from_directory(base_dir, 'index.html')

@app.route('/api/user-data', methods=['GET'])
def get_user_data():
    user_id = request.args.get('userId', 'test_user')
    data = {}
    if firebase_admin._apps:
        try:
            data = rtdb.reference(f"users/{user_id}").get() or {}
        except Exception:
            data = {}
    
    return jsonify({
        "status": "success",
        "balance": data.get("balance", 1000.0),
        "bonus": data.get("bonus", 0.0),
        "phone_number": data.get("phone_number", ""),
        "total_games_played": data.get("total_games_played", 0),
        "total_winnings": data.get("total_winnings", 0.0),
        "transactions": data.get("transactions", [])
    })

@app.route('/api/round', methods=['GET'])
def get_round():
    user_id = request.args.get('userId', 'test_user')
    return jsonify({
        "status": "success",
        "balance": wallet_instance.get_balance(user_id),
        "bonus": 0.0,
        "state": engine.get_state(user_id)
    })

@app.route('/api/round/pick', methods=['POST'])
def pick_cartel():
    data = request.get_json() or {}
    user_id = request.args.get('userId', 'test_user')
    ok, code = engine.pick(user_id, data.get('cartel'))
    return jsonify({
        "status": "success" if ok else "fail",
        "code": code,
        "balance": wallet_instance.get_balance(user_id),
        "state": engine.get_state(user_id)
    })

@app.route('/api/round/unpick', methods=['POST'])
def unpick_cartel():
    data = request.get_json() or {}
    user_id = request.args.get('userId', 'test_user')
    ok, code = engine.unpick(user_id, data.get('cartel'))
    return jsonify({
        "status": "success" if ok else "fail",
        "code": code,
        "balance": wallet_instance.get_balance(user_id),
        "state": engine.get_state(user_id)
    })

@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    players = []
    if firebase_admin._apps:
        try:
            all_users = rtdb.reference("users").get() or {}
            players = [
                {"name": u.get("first_name", "Player"), "cartels": u.get("total_games_played", 0)} 
                for u in all_users.values() if u.get("first_name") != "Bingo Bot"
            ]
            players.sort(key=lambda x: x["cartels"], reverse=True)
        except Exception as e:
            print(f"Leaderboard error: {e}")
            
    return jsonify({"status": "success", "leaderboard": players[:10]})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
