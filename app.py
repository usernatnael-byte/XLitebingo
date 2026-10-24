import os
import json
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
import game_engine

app = Flask(__name__, template_folder='.', static_folder='.')
CORS(app)

# Firebase ማስጀመር (Render Env Variable ത്തിലെ ስህተቶችን በራሱ የሚያስተካክል)
if not firebase_admin._apps:
    firebase_config = os.environ.get('FIREBASE_CREDENTIALS_JSON')
    if firebase_config:
        try:
            # ሬንደር ሊጨምራቸው የሚችላቸውን ተጨማሪ ኮቴሽኖች እና ክፍተቶች ማጽዳት
            firebase_config = firebase_config.strip()
            if (firebase_config.startswith("'") and firebase_config.endswith("'")) or \
               (firebase_config.startswith('"') and firebase_config.endswith('"')):
                firebase_config = firebase_config[1:-1]
            
            cred_dict = json.loads(firebase_config)
            
            # private_key ውስጥ ያሉት \n በትክክል መስመራቸውን እንዲጠብቁ ማድረግ
            if 'private_key' in cred_dict:
                cred_dict['private_key'] = cred_dict['private_key'].replace('\\n', '\n')
                
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            print("Firebase initialized successfully from Environment Variable!")
        except Exception as e:
            print(f"Firebase Init Error from Env: {e}")
    else:
        try:
            cred = credentials.Certificate("firebase_key.json")
            firebase_admin.initialize_app(cred)
            print("Firebase initialized successfully from local file!")
        except Exception as e:
            print(f"Firebase Init Error from File: {e}")

db = firestore.client() if firebase_admin._apps else None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({
        "status": "online",
        "message": "1x Bingo server is running successfully with Firebase & 2-player rule!"
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
