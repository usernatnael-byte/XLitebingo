from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
import time
import random

app = Flask(__name__)
CORS(app)

# የጨዋታው ሁኔታ (Game State)
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
    """እያንዳንዱን ቁጥር በ ሰኮንድ ልዩነት እየራገፈ ወደ ከረጢቱ የሚወስድ ሉፕ"""
    while True:
        if game_state["running"]:
            if game_state["bag"]:
                # ቁጥሩን በ int መልክ ብቻ መላኩን ማረጋገጥ (NaN እንዳይመጣ)
                ball = int(game_state["bag"].pop(0))
                game_state["current"] = ball
                game_state["called"].append(ball)
            else:
                game_state["running"] = False
        time.sleep(3)

# የጀርባ አሰራር (Background Thread) ማስጀመር
drawer_thread = threading.Thread(target=background_ball_drawer, daemon=True)
drawer_thread.start()

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
    data = request.json
    cartela_id = data.get('cartela_id')
    username = data.get('username', 'Nhatty')
    
    game_state["running"] = False
    game_state["winner"] = {
        "name": username,
        "cartela_id": cartela_id
    }
    
    return jsonify({
        "status": "success",
        "winner": game_state["winner"]
    })

@app.route('/reset', methods=['GET'])
def reset_endpoint():
    reset_game()
    return jsonify({"status": "reset"})

if __name__ == '__main__':
    # ሰርቨሩን በ Port 5001 ማስጀመር
    app.run(host='0.0.0.0', port=5001, debug=True)
