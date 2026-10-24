import os
import json
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
import game_engine

app = Flask(__name__, template_folder='.', static_folder='.')
CORS(app)

# Firebase ማስተካከል (ባዶ ከሆነ ሰርቨሩ እንዳይወድቅ በ Try-Except ተያዟል)
db = None
if not firebase_admin._apps:
    firebase_config = os.environ.get('FIREBASE_CREDENTIALS_JSON')
    if firebase_config and firebase_config.strip():
        try:
            firebase_config = firebase_config.strip()
            if (firebase_config.startswith("'") and firebase_config.endswith("'")) or \
               (firebase_config.startswith('"') and firebase_config.endswith('"')):
                firebase_config = firebase_config[1:-1]
            
            cred_dict = json.loads(firebase_config)
            if 'private_key' in cred_dict:
                cred_dict['private_key'] = cred_dict['private_key'].replace('\\n', '\n')
                
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("Firebase initialized successfully!")
        except Exception as e:
            print(f"Firebase Init Warning: {e} (Continuing without DB)")
    else:
        print("No Firebase Environment Variable found. Running without DB.")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({
        "status": "online",
        "message": "1x Bingo server is running successfully!"
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
