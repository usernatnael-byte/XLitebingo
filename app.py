import os
import json
import random
import threading
import time
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, db as rtdb

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}, r"/*": {"origins": "*"}})

# --- Firebase ማስጀመር (Render Env Variables) ---
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


# --- የጨዋታው ሁኔታ (Game State) ---
game_state = {
    "running": False,
    "round_id": 1,
    "current": None,
    "called": [],
    "bag": [],
    "winner": None
}

def reset_game():
    game_state["running"] = False
    game_state["current"] = None
    game_state["called"] = []
    game_state["bag"] = list(range(1, 76))
    random.shuffle(game_state["bag"])
    game_state["winner"] = None

# የመጀመሪያ ቦርሳ ማዘጋጀት
reset_game()

def background_ball_drawer():
    """እያንዳንዱን ቁጥር በ 3 ሰኮንድ ልዩነት እየራገፈ ወደ ከረጢቱ የሚወስድ ሉፕ"""
    while True:
        if game_state["running"]:
            if game_state["bag"]:
                ball = int(game_state["bag"].pop(0))
                game_state["current"] = ball
                game_state["called"].append(ball)
            else:
                game_state["running"] = False
        time.sleep(3)

# የጀርባ አሰራር (Background Thread) ማስጀመር
drawer_thread = threading.Thread(target=background_ball_drawer, daemon=True)
drawer_thread.start()


# --- API Endpoints ---

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
        "name": data.get("first_name", data.get("name", "Player")),
        "balance": data.get("balance", 20.0),
        "main_balance": data.get("main_balance", 0.0),
        "total_games_played": data.get("total_games_played", 0),
        "total_winnings_count": data.get("total_winnings_count", 0),
        "total_winnings": data.get("total_winnings", 0.0)
    })

@app.route('/state', methods=['GET'])
def get_state():
    return jsonify(game_state)

@app.route('/start', methods=['GET'])
def start_game():
    if not game_state["running"]:
        reset_game()
        game_state["running"] = True
        game_state["round_id"] += 1
    return jsonify({"status": "started", "round_id": game_state["round_id"]})

@app.route('/claim_bingo', methods=['POST'])
def claim_bingo():
    data = request.json or {}
    cartela_id = data.get('cartela_id')
    username = data.get('username', 'Player')
    user_id = data.get('userId', 'test_user')

    game_state["running"] = False
    
    # የሽልማት መጠን ማስላት (ለምሳሌ: በወጡ ቁጥሮች እና ካርቴሎች ብዛት ልክ)
    prize = len(game_state["called"]) * 10
    
    game_state["winner"] = {
        "name": username,
        "cartela_id": cartela_id,
        "prize": prize
    }

    # አሸናፊ ሲሆን ሽልማቱን ወደ ዩዘሩ Main Balance በፋየርቤዝ መመዝገብ
    if firebase_admin._apps:
        try:
            ref = rtdb.reference(f"users/{user_id}")
            user_data = ref.get() or {}
            current_main = float(user_data.get("main_balance", 0.0))
            current_total_win = float(user_data.get("total_winnings", 0.0))
            current_win_count = int(user_data.get("total_winnings_count", 0))
            current_games = int(user_data.get("total_games_played", 0))

            new_main = current_main + prize
            new_total_win = current_total_win + prize
            
            ref.update({
                "main_balance": new_main,
                "total_winnings": new_total_win,
                "total_winnings_count": current_win_count + 1,
                "total_games_played": current_games + 1
            })
        except Exception as e:
            print(f"Error updating winner data in DB: {e}")

    return jsonify({
        "status": "success",
        "winner": game_state["winner"]
    })

@app.route('/reset', methods=['GET'])
def reset_endpoint():
    reset_game()
    return jsonify({"status": "reset"})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
