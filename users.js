class FirestoreWallet {
    constructor(db) {
        this.db = db;
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

    async prepare_settlement(roundId, payouts) {
        await this.db.collection('rounds').doc(String(roundId)).set({
            status: 'settling',
            payouts,
            settlement_started_at: new Date().toISOString()
        }, { merge: true });
    }

    async record_round_result(roundId, result) {
        await this.db.collection('rounds').doc(String(roundId)).set({
            status: 'settled',
            round_id: String(roundId),
            players: Array.isArray(result.players) ? result.players : [],
            winners: Array.isArray(result.winners) ? result.winners : [],
            no_winner: Boolean(result.no_winner),
            pool: Number(result.pool || 0),
            settled_at: result.settled_at || new Date().toISOString()
        }, { merge: true });
    }

    async settle(roundId, payouts) {
        const roundRef = this.db.collection('rounds').doc(String(roundId));

        for (const [userId, rawAmount] of Object.entries(payouts || {})) {
            const amount = Number(rawAmount);
            if (!Number.isFinite(amount) || amount <= 0) continue;

            const userRef = this.db.collection('users').doc(String(userId));

            await this.db.runTransaction(async transaction => {
                const roundDoc = await transaction.get(roundRef);
                const userDoc = await transaction.get(userRef);
                if (!userDoc.exists) return;

                const roundData = roundDoc.exists ? roundDoc.data() : {};
                const settledUsers = roundData.settled_users || {};

                if (Object.prototype.hasOwnProperty.call(settledUsers, String(userId))) {
                    return;
                }

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
                    total_games_won: Number(data.total_games_won || 0) + 1,
                    transactions
                });

                transaction.set(roundRef, {
                    status: 'settling',
                    settled_users: {
                        ...settledUsers,
                        [String(userId)]: amount
                    }
                }, { merge: true });
            });

            this.cache_drop(userId);
        }

        await roundRef.set({
            status: 'settled',
            settled_at: new Date().toISOString()
        }, { merge: true });
    }

    async cancel_round(roundId, userIds) {
        for (const uid of [...new Set((userIds || []).map(String))]) {
            await this.refund(uid, String(roundId));
        }

        await this.db.collection('rounds').doc(String(roundId)).set({
            status: 'cancelled',
            cancelled_at: new Date().toISOString()
        }, { merge: true });
    }

    async profile(userId) {
        const doc = await this.db.collection('users').doc(String(userId)).get();
        return doc.exists ? doc.data() : null;
    }

    async recover_unsettled() {
        const snapshot = await this.db.collection('rounds').get();
        let recovered = 0;

        for (const doc of snapshot.docs) {
            const round = doc.data() || {};
            if (!['locked', 'drawing', 'settling'].includes(round.status)) continue;

            // A prepared settlement is safe to resume because each user's payout
            // is recorded transactionally and cannot be credited twice.
            if (round.status === 'settling' && round.payouts &&
                typeof round.payouts === 'object') {
                await this.settle(doc.id, round.payouts);
            } else {
                // If the process stopped before a complete payout was prepared,
                // refund every charged participant. refund() is idempotent.
                const ticketMap = round.tickets || round.snapshot || {};
                const userIds = [...new Set(Object.values(ticketMap).map(String))];
                await this.cancel_round(doc.id, userIds);
            }

            recovered++;
        }

        console.log(`Recovered ${recovered} unfinished round(s).`);
        return recovered;
    }
}

module.exports = FirestoreWallet;
