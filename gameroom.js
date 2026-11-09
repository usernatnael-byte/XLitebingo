const TICKET_PRICE = 10;
const PRIZE_PER_CARTEL = 8;
const MAX_SELECTION = 4;
const CARTEL_COUNT = 500;
const BALLS = 75;

const matrixCache = {};

function seededRandom(seed) {
    let x = Math.sin(seed) * 10000;
    return x - Math.floor(x);
}

function generateMatrix(ticketId) {
    if (matrixCache[ticketId]) return matrixCache[ticketId];

    let seed = ticketId * 1573;
    let matrix = [];

    for (let col = 0; col < 5; col++) {
        let numbers = [];
        let low = col * 15 + 1;

        while (numbers.length < 5) {
            let value = low + Math.floor(seededRandom(seed) * 15);
            seed++;

            if (!numbers.includes(value)) numbers.push(value);
        }

        matrix.push(numbers);
    }

    matrixCache[ticketId] = matrix;
    return matrix;
}

function checkBingo(m, drawnSet) {
    for (let r = 0; r < 5; r++) {
        if ([0,1,2,3,4].every(c => (r === 2 && c === 2) || drawnSet.has(m[c][r]))) {
            return true;
        }
    }

    for (let c = 0; c < 5; c++) {
        if ([0,1,2,3,4].every(r => (r === 2 && c === 2) || drawnSet.has(m[c][r]))) {
            return true;
        }
    }

    if ([0,1,2,3,4].every(i => i === 2 || drawnSet.has(m[i][i]))) {
        return true;
    }

    if ([0,1,2,3,4].every(i => i === 2 || drawnSet.has(m[4 - i][i]))) {
        return true;
    }

    if (
        drawnSet.has(m[0][0]) &&
        drawnSet.has(m[4][0]) &&
        drawnSet.has(m[0][4]) &&
        drawnSet.has(m[4][4])
    ) {
        return true;
    }

    return false;
}

function maskPhone(phone) {
    let digits = String(phone || '').replace(/\D/g, '');
    return digits.length >= 4 ? '***' + digits.slice(-4) : '';
}

class GameEngine {
    constructor(wallet, min_players = 2, selection_seconds = 30, draw_interval = 2.0, result_seconds = 10) {
        this.wallet = wallet;
        this.min_players = Math.max(1, min_players);
        this.selection_seconds = selection_seconds;
        this.draw_interval = draw_interval;
        this.result_seconds = result_seconds;
        this.first_draw_delay = 3.0;

        this._seq = 0;
        this._threadRunning = false;
        this.on_round_result = null;

        this._newRound();
    }

    start() {
        this._threadRunning = true;
        this._runLoop();

        console.log(`🎰 Game engine started (min players: ${this.min_players})`);
    }

    stop() {
        this._threadRunning = false;
    }

    async _runLoop() {
        while (this._threadRunning) {
            try {
                await this._tick();
            } catch (e) {
                console.error('Engine tick error:', e);
            }

            await new Promise(resolve => setTimeout(resolve, 200));
        }
    }

    _newRound() {
        let now = Date.now() / 1000;

        this.round_id = `r${Math.floor(now * 1000)}`;
        this.phase = 'selection';
        this.phase_ends_at = now + this.selection_seconds;
        this.cartels = {};
        this.draw_order = [];
        this.drawn = [];
        this.next_draw_at = null;
        this.winners = [];
        this.no_winner = false;
        this._pending = null;

        this._seq++;
    }

    async pick(uid, cartel) {
        uid = String(uid);

        if (typeof cartel !== 'number' || cartel < 1 || cartel > CARTEL_COUNT) {
            return [false, 'invalid'];
        }

        if (this.phase !== 'selection') return [false, 'phase'];

        if (this.cartels[cartel] === uid) return [true, 'ok'];
        if (this.cartels[cartel]) return [false, 'taken'];

        let myCount = Object.values(this.cartels).filter(u => u === uid).length;

        if (myCount >= MAX_SELECTION) return [false, 'full'];

        try {
            let balance = await this.wallet.get_balance(uid);

            if (balance < (myCount + 1) * TICKET_PRICE) {
                return [false, 'balance'];
            }
        } catch (e) {
            return [false, 'error'];
        }

        if (this.phase !== 'selection') return [false, 'phase'];

        this.cartels[cartel] = uid;
        this._seq++;

        return [true, 'ok'];
    }

    unpick(uid, cartel) {
        uid = String(uid);

        if (this.phase !== 'selection') return [false, 'phase'];

        if (this.cartels[cartel] === uid) {
            delete this.cartels[cartel];
            this._seq++;
        }

        return [true, 'ok'];
    }

    get_state(uid) {
        uid = String(uid);

        let mine = Object.keys(this.cartels)
            .filter(c => this.cartels[c] === uid)
            .map(Number);

        let winners = [];

        if (this.phase === 'result') {
            winners = this.winners.map(w => ({
                ...w,
                mine: w.uid === uid
            }));
        }

        return {
            round_id: this.round_id,
            seq: this._seq,
            phase: this.phase,
            server_time: Date.now() / 1000,
            phase_ends_at: ['selection', 'result'].includes(this.phase) ? this.phase_ends_at : null,
            selection_seconds: this.selection_seconds,
            result_seconds: this.result_seconds,
            min_players: this.min_players,
            players: new Set(Object.values(this.cartels)).size,
            taken: Object.keys(this.cartels).map(Number),
            my_cartels: mine,
            pool: Object.keys(this.cartels).length * PRIZE_PER_CARTEL,
            drawn: this.drawn,
            winners: winners,
            no_winner: this.phase === 'result' ? this.no_winner : false
        };
    }

    async _tick() {
        let now = Date.now() / 1000;

        if (this.phase === 'selection') {
            if (now >= this.phase_ends_at) {
                let activePlayers = new Set(Object.values(this.cartels)).size;

                if (activePlayers < this.min_players) {
                    this.phase_ends_at = now + this.selection_seconds;
                    this._seq++;
                } else {
                    this.phase = 'locking';
                    this._seq++;

                    await this._do_lock(this.cartels);
                }
            }
        } else if (this.phase === 'drawing') {
            if (now >= this.next_draw_at) {
                this._draw_one(now);
            }

            if (this.phase === 'settling') {
                await this._do_settle();
            }
        } else if (this.phase === 'settling') {
            await this._do_settle();
        } else if (this.phase === 'result') {
            if (now >= this.phase_ends_at) {
                this._newRound();
            }
        }
    }

    async _do_lock(snapshot) {
        let rid = this.round_id;

        await this.wallet.begin_round(rid, snapshot);

        let byUser = {};

        for (let [cartel, uid] of Object.entries(snapshot)) {
            if (!byUser[uid]) byUser[uid] = [];
            byUser[uid].push(Number(cartel));
        }

        let paid = {};

        for (let [uid, cartels] of Object.entries(byUser)) {
            let res = await this.wallet.charge(
                uid,
                cartels.length * TICKET_PRICE,
                rid,
                cartels.length
            );

            if (res !== null) {
                for (let c of cartels) paid[c] = uid;
            } else {
                await this.wallet.refund(uid, rid);
            }
        }

        if (new Set(Object.values(paid)).size < this.min_players) {
            await this.wallet.cancel_round(
                rid,
                [...new Set(Object.values(paid))]
            );

            this.cartels = {};
            this.phase = 'selection';
            this.phase_ends_at = Date.now() / 1000 + this.selection_seconds;

            return;
        }

        this.cartels = paid;

        let order = Array.from({ length: BALLS }, (_, i) => i + 1);

        for (let i = order.length - 1; i > 0; i--) {
            let j = Math.floor(Math.random() * (i + 1));
            [order[i], order[j]] = [order[j], order[i]];
        }

        this.draw_order = order;
        this.drawn = [];
        this.phase = 'drawing';
        this.next_draw_at = Date.now() / 1000 + this.first_draw_delay;

        this._seq++;
    }

    _draw_one(now) {
        let number = this.draw_order[this.drawn.length];

        this.drawn.push(number);
        this._seq++;

        let drawnSet = new Set(this.drawn);
        let winning = [];

        for (let [cartel, uid] of Object.entries(this.cartels)) {
            if (checkBingo(generateMatrix(Number(cartel)), drawnSet)) {
                winning.push(Number(cartel));
            }
        }

        if (winning.length > 0) {
            this._pending = ['win', winning];
            this.phase = 'settling';
        } else if (this.drawn.length >= BALLS) {
            this._pending = ['none', []];
            this.phase = 'settling';
        } else {
            this.next_draw_at = Math.max(
                this.next_draw_at + this.draw_interval,
                now
            );
        }
    }

    async _do_settle() {
        let rid = this.round_id;
        let tickets = { ...this.cartels };
        let pending = this._pending;
        let pool = 0;

        if (pending[0] === 'win') {
            let wins = pending[1];

            pool = Object.keys(tickets).length * PRIZE_PER_CARTEL;

            let share = Math.round((pool / wins.length) * 100) / 100;
            let payouts = {};

            for (let c of wins) {
                let uid = tickets[c];
                payouts[uid] = (payouts[uid] || 0) + share;
            }

            let profiles = {};

            for (let uid of Object.keys(payouts)) {
                profiles[uid] = await this.wallet.profile(uid) || {};
            }

            await this.wallet.settle(rid, payouts);

            this.winners = wins.map(c => ({
                uid: tickets[c],
                cartel: c,
                prize: share,
                name: profiles[tickets[c]].name || 'Player',
                username: profiles[tickets[c]].username,
                phone: maskPhone(profiles[tickets[c]].phone)
            }));

            this.no_winner = false;
        } else {
            await this.wallet.cancel_round(
                rid,
                [...new Set(Object.values(tickets))]
            );

            this.winners = [];
            this.no_winner = true;
        }

        this.phase = 'result';
        this.phase_ends_at = Date.now() / 1000 + this.result_seconds;

        this._seq++;

        if (this.on_round_result) {
            this.on_round_result({
                round_id: rid,
                players: new Set(Object.values(tickets)).size,
                cartels: Object.keys(tickets).length,
                pool: pool,
                balls: this.drawn.length,
                no_winner: this.no_winner,
                winners: this.winners
            });
        }
    }
}

module.exports = {
    GameEngine,
    TICKET_PRICE,
    PRIZE_PER_CARTEL,
    MAX_SELECTION,
    generateMatrix
};
