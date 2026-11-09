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
        const doc = await this.db.collection('users').doc(String(userId)).get();
        if (!doc.exists) return 0.0;
        const data = doc.data();
        const balance = Number(data.balance || 0);
        const bonus = Number(data.bonus || 0);
        this.cache_set(userId, balance, bonus);
        return balance + bonus;
    }

    async begin_round(roundId, snapshot) {
        await this.db.collection('rounds').doc(String(roundId)).set({
            status: 'locked',
            snapshot: snapshot,
            at: new Date().toISOString()
        });
    }

    async charge(userId, amount, roundId, cartels = 1) {
        amount = Number(amount);
        if (!Number.isFinite(amount) || amount <= 0) return null;
        const userRef = this.db.collection('users').doc(String(userId));

        const res = await this.db.runTransaction(async (transaction) => {
            const userDoc = await transaction.get(userRef);
            if (!userDoc.exists) return null;

            const data = userDoc.data();
            const balance = Number(data.balance || 0);
            const bonus = Number(data.bonus || 0);

            if (balance + bonus + 1e-9 < amount) return null;

            const fromBonus = Math.min(bonus, amount);
            const fromMain = amount - fromBonus;
            const newBalance = Math.max(0, balance - fromMain);
            const newBonus = Math.max(0, bonus - fromBonus);
            const weeklyCartels = (Number(data.weekly_cartels) || 0) + cartels;
            const txs = Array.isArray(data.transactions) ? [...data.transactions] : [];

            txs.push({
                type: 'play',
                amount,
                bonus_amount: fromBonus,
                main_amount: fromMain,
                round_id: roundId,
                timestamp: new Date().toISOString()
            });

            transaction.update(userRef, {
                balance: newBalance,
                bonus: newBonus,
                weekly_cartels: weeklyCartels,
                transactions: txs
            });

            return { balance: newBalance, bonus: newBonus };
        });

        if (res !== null) this.cache_drop(userId);
        return res;
    }

    async refund(userId, roundId) {
        const userRef = this.db.collection('users').doc(String(userId));

        await this.db.runTransaction(async (transaction) => {
            const userDoc = await transaction.get(userRef);
            if (!userDoc.exists) return;

            const data = userDoc.data();
            const txs = Array.isArray(data.transactions) ? [...data.transactions] : [];
            const roundTx = txs.find(t => t.round_id === roundId && t.type === 'play');
            const alreadyRefunded = txs.some(t => t.round_id === roundId && t.type === 'refund');

            if (!roundTx || alreadyRefunded) return;

            const bonusRefund = Number(roundTx.bonus_amount || 0);
            const mainRefund = roundTx.main_amount == null
                ? Number(roundTx.amount || 0)
                : Number(roundTx.main_amount || 0);

            transaction.update(userRef, {
                balance: Number(data.balance || 0) + mainRefund,
                bonus: Number(data.bonus || 0) + bonusRefund,
                transactions: [...txs, {
                    type: 'refund',
                    amount: bonusRefund + mainRefund,
                    bonus_amount: bonusRefund,
                    main_amount: mainRefund,
                    round_id: roundId,
                    timestamp: new Date().toISOString()
                }]
            });
        });

        this.cache_drop(userId);
    }

    async add_bonus(userId, amount, source = 'bonus') {
        amount = Number(amount);
        if (!Number.isFinite(amount) || amount <= 0) {
            throw new Error('Bonus amount must be greater than zero.');
        }

        const userRef = this.db.collection('users').doc(String(userId));

        await this.db.runTransaction(async (transaction) => {
            const userDoc = await transaction.get(userRef);
            if (!userDoc.exists) throw new Error('User not found.');

            const data = userDoc.data();
            const txs = Array.isArray(data.transactions) ? [...data.transactions] : [];

            txs.push({
                type: 'bonus',
                amount,
                source,
                timestamp: new Date().toISOString()
            });

            transaction.update(userRef, {
                bonus: Number(data.bonus || 0) + amount,
                transactions: txs
            });
        });

        this.cache_drop(userId);
    }

    async start_drawing(roundId, tickets) {
        await this.db.collection('rounds').doc(String(roundId)).update({
            status: 'drawing',
            tickets
        });
    }

    async settle(roundId, payouts) {
        const roundRef = this.db.collection('rounds').doc(String(roundId));

        for (const [userId, rawAmount] of Object.entries(payouts)) {
            const amount = Number(rawAmount);
            if (!Number.isFinite(amount) || amount <= 0) continue;

            const userRef = this.db.collection('users').doc(String(userId));

            await this.db.runTransaction(async transaction => {
                const roundDoc = await transaction.get(roundRef);
                const userDoc = await transaction.get(userRef);
                if (!userDoc.exists) return;

                const roundData = roundDoc.exists ? roundDoc.data() : {};
                const settledUsers = roundData.settled_users || {};

                if (settledUsers[String(userId)]) return;

                const data = userDoc.data();
                const transactions = Array.isArray(data.transactions) ? [...data.transactions] : [];

                transactions.push({
                    type: 'win',
                    amount,
                    round_id: String(roundId),
                    timestamp: new Date().toISOString()
                });

                transaction.update(userRef, {
                    balance: Number(data.balance || 0) + amount,
                    total_winnings: Number(data.total_winnings || 0) + amount,
                    transactions
                });

                transaction.set(roundRef, {
                    settled_users: { ...settledUsers, [String(userId)]: amount },
                    status: 'settled'
                }, { merge: true });
            });

            this.cache_drop(userId);
        }
    }

    async cancel_round(roundId, userIds) {
        for (const uid of userIds) {
            await this.refund(uid, roundId);
        }
    }

    async profile(userId) {
        const doc = await this.db.collection('users').doc(String(userId)).get();
        return doc.exists ? doc.data() : null;
    }

    async recover_unsettled() {
        return 0;
    }
}

module.exports = FirestoreWallet;
