import os
import json
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
import game_engine

app = Flask(__name__, template_folder='.', static_folder='.')
CORS(app)

# Firebase ማስተካከል (Render ላይ ያሉትን የተነጣጠሉ Environment Variables በቀጥታ የሚወስድ)
db = None
if not firebase_admin._apps:
    try:
        project_id = os.environ.get('FIREBASE_PROJECT_ID')
        private_key = os.environ.get('FIREBASE_PRIVATE_KEY')
        client_email = os.environ.get('FIREBASE_CLIENT_EMAIL')

        if project_id and private_key and client_email:
            # የ private_key መስመር መቀየሪያዎችን (\n) ማስተካከል
            if private_key.startswith('"') and private_key.endswith('"'):
                private_key = private_key[1:-1]
            private_key = private_key.replace('\\n', '\n')
            
            cred_dict = {
                "type": "service_account",
                "project_id": project_id,
                "private_key": private_key,
                "client_email": client_email
            }
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("Firebase initialized successfully from separate environment variables!")
        else:
            # ፋይሉን ወይም ነጠላ ጃሰን ለመጠቀም ሞክር
            firebase_config = os.environ.get('FIREBASE_CREDENTIALS_JSON')
            if firebase_config and firebase_config.strip():
                firebase_config = firebase_config.strip()
                cred_dict = json.loads(firebase_config)
                if 'private_key' in cred_dict:
                    cred_dict['private_key'] = cred_dict['private_key'].replace('\\n', '\n')
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                db = firestore.client()
                print("Firebase initialized from JSON env variable!")
            else:
                cred = credentials.Certificate("firebase_key.json")
                firebase_admin.initialize_app(cred)
                db = firestore.client()
                print("Firebase initialized from local file!")
    except Exception as e:
        print(f"Firebase Init Warning: {e} (Continuing without DB)")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({
        "status": "online",
        "message": "1x Bingo server is running successfully with Firebase!"
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
