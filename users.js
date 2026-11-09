const admin = require('firebase-admin');

class FirestoreWallet {
    constructor(db, firestore) {
        this.db = db;
        this.firestore = firestore;
        this.cache = new Map();
    }

    cache_set(userId, balance, bonus) {
        this.cache.set(String(userId), { balance: Number(balance), bonus: Number(bonus), at: Date.now() });
    }

    cache_drop(userId) {
        this.cache.delete(String(userId));
    }

    get_wallets(userId) {
        const cached = this.cache.get(String(userId));
        if (cached && Date.now() - cached.at < 60000) {
            return [cached.balance, cached.bonus];
        }
        return null;
    }

    async get_balance(userId) {
        const doc = await this.db.collection('users').document(String(userId)).get();
        if (!doc.exists) return 0.0;
        const data = doc.data();
        const balance = Number(data.balance || 0);
        const bonus = Number(data.bonus || 0);
        this.cache_set(userId, balance, bonus);
        return balance;
    }

    async begin_round(roundId, snapshot) {
        await this.db.collection('rounds').document(String(roundId)).set({
            status: 'locked',
            snapshot: snapshot,
            at: new Date().toISOString()
        });
    }

    async charge(userId, amount, roundId, cartels = 1) {
        const userRef = this.db.collection('users').document(String(userId));
        const res = await this.db.runTransaction(async (transaction) => {
            const userDoc = await transaction.get(userRef);
            if (!userDoc.exists) return null;
            const data = userDoc.data();
            let balance = Number(data.balance || 0);
            let bonus = Number(data.bonus || 0);
            
            if (balance < amount) return null;

            let fromBonus = Math.min(bonus, amount);
            let newBalance = balance - amount;
            let newBonus = bonus - fromBonus;
            let weeklyCartels = (Number(data.weekly_cartels) || 0) + cartels;

            const txs = data.transactions || [];
            txs.push({
                type: 'play',
                amount: amount,
                round_id: roundId,
                timestamp: new Date().toISOString() + "Z"
            });

            transaction.update(userRef, {
                balance: newBalance,
                bonus: newBonus,
                weekly_cartels: weeklyCartels,
                transactions: txs
            });

            return newBalance;
        });

        if (res !== null) {
            this.cache_drop(userId);
        }
        return res;
    }

    async refund(userId, roundId) {
        const userRef = this.db.collection('users').document(String(userId));
        await this.db.runTransaction(async (transaction) => {
            const userDoc = await transaction.get(userRef);
            if (!userDoc.exists) return;
            const data = userDoc.data();
            const txs = data.transactions || [];
            const roundTx = txs.find(t => t.round_id === roundId && t.type === 'play');
            if (roundTx) {
                const refundAmount = roundTx.amount;
                transaction.update(userRef, {
                    balance: Number(data.balance || 0) + refundAmount,
                    transactions: [...txs, { type: 'refund', amount: refundAmount, round_id: roundId, timestamp: new Date().toISOString() + "Z" }]
                });
            }
        });
        this.cache_drop(userId);
    }

    async start_drawing(roundId, tickets) {
        await this.db.collection('rounds').document(String(roundId)).update({ status: 'drawing', tickets });
    }

    async settle(roundId, payouts) {
        const batch = this.db.batch();
        for (const [userId, amount] of Object.entries(payouts)) {
            const userRef = this.db.collection('users').document(String(userId));
            const userDoc = await userRef.get();
            if (userDoc.exists) {
                const data = userDoc.data();
                const newBalance = Number(data.balance || 0) + amount;
                const totalWins = Number(data.total_winnings || 0) + amount;
                const txs = data.transactions || [];
                txs.push({ type: 'win', amount: amount, round_id: roundId, timestamp: new Date().toISOString() + "Z" });
                
                batch.update(userRef, {
                    balance: newBalance,
                    total_winnings: totalWins,
                    transactions: txs
                });
            }
        }
        await batch.commit();
        for (const userId of Object.keys(payouts)) this.cache_drop(userId);
    }

    async cancel_round(roundId, userIds) {
        for (const uid of userIds) {
            await this.refund(uid, roundId);
        }
    }

    async profile(userId) {
        const doc = await this.db.collection('users').document(String(userId)).get();
        return doc.exists ? doc.data() : null;
    }

    async recover_unsettled() {
        return 0;
    }
}

module.exports = FirestoreWallet;
