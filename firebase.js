const admin = require('firebase-admin');
const fs = require('fs');
const path = require('path');
const createRealtimeStore = require('./rtdb-store');

const secretCandidates = [
    process.env.FIREBASE_KEY_PATH,
    '/etc/secrets/firebase_key.json',
    path.join(__dirname, 'firebase_key.json')
].filter(Boolean);

const keyPath = secretCandidates.find(candidate => fs.existsSync(candidate));
if (!keyPath) {
    throw new Error('Firebase service account file not found. Set FIREBASE_KEY_PATH=/etc/secrets/firebase_key.json in Render.');
}

if (!admin.apps.length) {
    admin.initializeApp({
        credential: admin.credential.cert(require(keyPath)),
        databaseURL: process.env.FIREBASE_DATABASE_URL || 'https://litebingo-513a9-default-rtdb.firebaseio.com'
    });
}

const realtimeDb = admin.database();
const db = createRealtimeStore(realtimeDb);

module.exports = { admin, db, realtimeDb };
