const express = require('express');
const cors = require('cors');
const path = require('path');
const FirestoreWallet = require('./users');
const { GameEngine } = require('./gameroom');
const admin = require('firebase-admin');

if (!admin.apps.length) {
    admin.initializeApp({
        credential: admin.credential.cert(require('./firebase_key.json'))
    });
}
const db = admin.firestore();

const app = express();
app.use(cors());
app.use(express.json());

const wallet = new FirestoreWallet(db, admin.firestore);
const engine = new GameEngine(wallet, 2);
engine.start();

// ማስገቢያ ዌብ አፕ ገጽ
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

app.get('/health', (req, res) => {
    res.json({ status: "ok" });
});

app.get('/api/round', (req, res) => {
    const userId = req.headers['x-telegram-user-id'] || 'test_user';
    res.json({
        status: "success",
        state: engine.get_state(userId)
    });
});

app.post('/api/round/pick', async (req, res) => {
    const userId = req.headers['x-telegram-user-id'] || 'test_user';
    const { cartel } = req.body;
    const [ok, code] = await engine.pick(userId, cartel);
    res.json({
        status: ok ? "success" : "error",
        code: code,
        state: engine.get_state(userId)
    });
});

app.post('/api/round/unpick', (req, res) => {
    const userId = req.headers['x-telegram-user-id'] || 'test_user';
    const { cartel } = req.body;
    const [ok, code] = engine.unpick(userId, cartel);
    res.json({
        status: ok ? "success" : "error",
        code: code,
        state: engine.get_state(userId)
    });
});

app.get('/api/user-data', async (req, res) => {
    const userId = req.query.userId || req.headers['x-telegram-user-id'] || 'test_user';
    try {
        const doc = await db.collection('users').document(String(userId)).get();
        const data = doc.exists ? doc.data() : {};
        res.json({
            status: "success",
            balance: data.balance || 0,
            bonus: data.bonus || 0,
            transactions: data.transactions || [],
            phone_number: data.phone_number,
            first_name: data.first_name,
            total_games_played: data.total_games_played || 0,
            total_winnings: data.total_winnings || 0
        });
    } catch (e) {
        res.status(500).json({ status: "error", message: e.message });
    }
});

app.get('/api/leaderboard', async (req, res) => {
    try {
        const snapshot = await db.collection('users').orderBy('weekly_cartels', 'desc').limit(10).get();
        let leaderboard = [];
        snapshot.forEach(doc => {
            let data = doc.data();
            leaderboard.push({
                name: data.username || data.first_name || "Player",
                cartels: data.weekly_cartels || 0
            });
        });
        res.json({ status: "success", leaderboard });
    } catch (e) {
        res.json({ status: "success", leaderboard: [] });
    }
});

const PORT = process.env.PORT || 5500;
app.listen(PORT, () => {
    console.log(`🌐 WebApp API running on port ${PORT}!`);
});

// Telegram Bot-ን ከሰርቨሩ ጋር ማቀናጀት
require('./bot.js');

module.exports = { app, engine, wallet };
