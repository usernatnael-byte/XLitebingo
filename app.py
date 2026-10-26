import os
import firebase_admin
from firebase_admin import credentials, db
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from game_engine import GameEngine, CARTEL_COUNT, TICKET_PRICE

app = Flask(__name__)
CORS(app)

# Firebase Admin SDK ማዋቀር (በ Render Secret Files ውስጥ ያስገባነውን firebase-key.json እንጠቀማለን)
# Project ID: ethio-bingo-app[span_2](start_span)[span_2](end_span)
cred = credentials.Certificate("firebase-key.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://ethio-bingo-app-default-rtdb.firebaseio.com/'
})

# ---------------------------------------------------------------------
# FIREBASE WALLET & DATABASE BRIDGE
# ---------------------------------------------------------------------
class FirebaseWallet:
    def recover_unsettled(self):
        ref = db.reference('rounds')
        rounds = ref.get() or {}
        refunded_count = 0
        for rid, rdata in rounds.items():
            if rdata.get('status') in ['started', 'locked']:
                db.reference(f'rounds/{rid}').update({'status': 'aborted'})
                refunded_count += 1
        return refunded_count

    def get_balance(self, uid):
        user_ref = db.reference(f'users/{uid}')
        data = user_ref.get() or {}
        if 'balance' not in data:
            initial_balance = 100.0  # ለአዲስ ተጠቃሚ የሚሰጥ የሙከራ ሒሳብ
            user_ref.update({'balance': initial_balance})
            return initial_balance
        return float(data.get('balance', 0.0))

    def profile(self, uid):
        user_ref = db.reference(f'users/{uid}')
        data = user_ref.get() or {}
        return {
            "name": data.get("name", "Player"),
            "username": data.get("username", ""),
            "phone": data.get("phone", "Not Provided")
        }

    def begin_round(self, rid, snapshot):
        db.reference(f'rounds/{rid}').set({'status': 'locked', 'snapshot': snapshot})

    def charge(self, uid, amount, rid, cartels=1):
        user_ref = db.reference(f'users/{uid}')
        balance = self.get_balance(uid)
        if balance + 1e-9 < amount:
            return None
        new_balance = balance - amount
        user_ref.update({'balance': new_balance})
        
        # የግብይት ታሪክ መመዝገቢያ
        db.reference(f'users/{uid}/transactions').push({
            'type': 'ticket_purchase',
            'amount': amount,
            'timestamp': {'.sv': 'timestamp'}
        })
        return new_balance

    def refund(self, uid, rid):
        user_ref = db.reference(f'users/{uid}')
        current = self.get_balance(uid)
        user_ref.update({'balance': current + TICKET_PRICE})
        db.reference(f'users/{uid}/transactions').push({
            'type': 'refund',
            'amount': TICKET_PRICE,
            'timestamp': {'.sv': 'timestamp'}
        })

    def start_drawing(self, rid, tickets):
        db.reference(f'rounds/{rid}').update({'status': 'drawing', 'tickets': tickets})

    def settle(self, rid, payouts):
        db.reference(f'rounds/{rid}').update({'status': 'settled', 'payouts': payouts})
        for uid, prize in payouts.items():
            user_ref = db.reference(f'users/{uid}')
            current_bal = self.get_balance(uid)
            user_ref.update({'balance': current_bal + prize})
            
            db.reference(f'users/{uid}/transactions').push({
                'type': 'win',
                'amount': prize,
                'timestamp': {'.sv': 'timestamp'}
            })
            
            data = user_ref.get() or {}
            total_win = float(data.get('total_winnings', 0.0)) + prize
            games_won = int(data.get('games_won', 0)) + 1
            user_ref.update({'total_winnings': total_win, 'games_won': games_won})

    def cancel_round(self, rid, uids):
        db.reference(f'rounds/{rid}').update({'status': 'cancelled'})

# ጌም ኢንጂኑን ከፋየርቤዝ वालेት ጋር ማስጀመር
wallet = FirebaseWallet()
engine = GameEngine(wallet=wallet, min_players=1)
engine.start()

# ---------------------------------------------------------------------
# FLASK ROUTES
# ---------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/round', methods=['GET'])
def get_round():
    uid = request.headers.get('X-Telegram-Init-Data', 'test_user')
    state = engine.get_state(uid)
    balance = wallet.get_balance(uid)
    return jsonify({'status': 'success', 'state': state, 'balance': balance, 'bonus': 0.0})

@app.route('/api/round/pick', methods=['POST'])
def pick_cartel():
    data = request.get_json() or {}
    cartel = data.get('cartel')
    uid = request.headers.get('X-Telegram-Init-Data', 'test_user')
    ok, code = engine.pick(uid, cartel)
    balance = wallet.get_balance(uid)
    return jsonify({'status': 'success' if ok else 'error', 'code': code, 'balance': balance, 'state': engine.get_state(uid)})

@app.route('/api/round/unpick', methods=['POST'])
def unpick_cartel():
    data = request.get_json() or {}
    cartel = data.get('cartel')
    uid = request.headers.get('X-Telegram-Init-Data', 'test_user')
    ok, code = engine.unpick(uid, cartel)
    balance = wallet.get_balance(uid)
    return jsonify({'status': 'success' if ok else 'error', 'code': code, 'balance': balance, 'state': engine.get_state(uid)})

@app.route('/api/user-data', methods=['GET'])
def user_data():
    uid = request.args.get('userId', 'test_user')
    profile_data = wallet.profile(uid)
    balance = wallet.get_balance(uid)
    
    txs_ref = db.reference(f'users/{uid}/transactions')
    txs = txs_ref.get() or {}
    tx_list = list(txs.values()) if isinstance(txs, dict) else []
    
    user_ref = db.reference(f'users/{uid}')
    udata = user_ref.get() or {}

    return jsonify({
        'status': 'success',
        'balance': balance,
        'bonus': 0.0,
        'phone_number': profile_data.get('phone', 'Not Provided'),
        'total_games_played': udata.get('games_played', 0),
        'total_winnings': udata.get('total_winnings', 0.0),
        'transactions': tx_list
    })

@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    users_ref = db.reference('users')
    users = users_ref.get() or {}
    leaderboard_data = []
    for uid, udata in users.items():
        leaderboard_data.append({
            'name': udata.get('name', 'Player'),
            'cartels': udata.get('games_won', 0)
        })
    leaderboard_data = sorted(leaderboard_data, key=lambda x: x['cartels'], reverse=True)[:10]
    return jsonify({'status': 'success', 'leaderboard': leaderboard_data})

@app.route('/api/send-support', methods=['POST'])
def send_support():
    return jsonify({'status': 'success'})

@app.route('/api/send-rules', methods=['POST'])
def send_rules():
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
