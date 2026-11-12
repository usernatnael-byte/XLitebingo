const TICKET_PRICE = 10;
const PRIZE_PER_CARTEL = 8;
const MAX_SELECTION = 4;
const CARTEL_COUNT = 500;
const BALLS = 75;

const matrixCache = {};

// 🟢 100% ንጹህ እና ልዩ (Unique) የሆኑ የኢትዮጵያዊያን የወንድ ስሞች ብቻ (First Names Only)
const ETHIOPIAN_MALE_NAMES = [
    "Kebede", "Dawit", "Yonas", "Kemal", "Natnael", "Fikru", "Samuel", "Mikiyas", 
    "Endale", "Birhanu", "Anwar", "Amare", "Eyob", "Adnew", "Belachew", "Getachew", 
    "Sintayehu", "Tadesse", "Teferi", "Alemayehu", "Beyene", "Dessalegn", "Eshetu", 
    "Fantahun", "Gizaw", "Habtamu", "Linsa", "Mohammed", "Assefa", "Tamirat", "Worku", 
    "Abraham", "Biniyam", "Dagmawi", "Firon", "Geremew", "Kokeb", "Oliyad", "Petros", 
    "Qumneger", "Sendek", "Temesgen", "Wubshet", "Yacob", "Kiros", "Paulos", "Aklilu", 
    "Kasahun", "Mesay", "Nati", "Walelign", "Yonatan", "Abiy", "Dereje", "Elias", 
    "Gezahegn", "Yibekal", "Nahusenay", "Tefera", "Yared", "Fikadu", "Teklehaimanot", 
    "Jamal", "Robel", "Dejene", "Anbese", "Amare", "Girma", "Umer", "Sultan", 
    "Birhanu", "Bogale", "Migbu", "Abrha", "Bilal", "Ayele", "Nasir", "Estifanos", 
    "Admassu", "Hassen", "Ahmed", "Mustefa", "Mokonnen", "Bekele", "Tesfaye", "Mekonnen", 
    "Mehari", "Ayalew", "Mihret", "Woldesenbet", "Ibrahim", "Lucas", "Yisak", "Beinesu", 
    "Ali", "Bila", "Gessesse", "Ginbaru", "Muluken", "Markos", "Emru", "Abdul", 
    "Kadija", "Haile", "Takele", "Assefaw", "Bitew", "Naol", "Mebratu", "Abdu"
];

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

class GameEngine {
    constructor(wallet, min_players = 2, selection_seconds = 30, draw_interval = 3.0, result_seconds = 10) {
        this.wallet = wallet;
        this.min_players = Math.max(1, min_players);
        this.selection_seconds = selection_seconds;
        this.draw_interval = draw_interval;
        this.result_seconds = result_seconds;
        this.first_draw_delay = 3.0;

        this._seq = 0;
        this._threadRunning = false;
        this.on_round_result = null;

        this.botSettings = {
            botCount: 50,
            botWinPercent: 20,
            botCardsPerUser: 2,
            restrictDepositedWin: true
        };

        this._newRound();
    }

    setBotSettings(settings) {
        if (settings) {
            this.botSettings = { ...this.botSettings, ...settings };
        }
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
        this.botProfiles = {};
        this.restrictedUsers = new Set();
        this.draw_order = [];
        this.drawn = [];
        this.next_draw_at = null;
        this.winners = [];
        this.no_winner = false;
        this._pending = null;
        this._botsInjected = false;
        this.botQueue = [];
        this.botInjectIndex = 0;

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
                name: w.name || 'Player',
                cartel: w.cartel,
                prize: w.prize,
                mine: w.uid === uid
            }));
        }

        const uniquePlayers = new Set(Object.values(this.cartels));

        return {
            round_id: this.round_id,
            seq: this._seq,
            phase: this.phase,
            server_time: Date.now() / 1000,
            phase_ends_at: ['selection', 'result'].includes(this.phase) ? this.phase_ends_at : null,
            selection_seconds: this.selection_seconds,
            result_seconds: this.result_seconds,
            min_players: this.min_players,
            players: uniquePlayers.size,
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
            if (!this._botsInjected) {
                this._initBotsQueue();
                this._botsInjected = true;
            }

            this._processBotQueue();

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

    _initBotsQueue() {
        const targetBotCount = Math.min(400, Math.max(0, this.botSettings.botCount || 0));
        const cardsPerBot = Math.min(4, Math.max(1, this.botSettings.botCardsPerUser || 2));
        this.botProfiles = {};
        this.botQueue = [];

        let shuffledNames = [...ETHIOPIAN_MALE_NAMES].sort(() => Math.random() - 0.5);

        for (let i = 0; i < targetBotCount; i++) {
            const botId = `bot_${i + 1}`;
            const randomName = shuffledNames[i % shuffledNames.length];

            this.botProfiles[botId] = { name: randomName };

            const howManyCards = Math.floor(Math.random() * cardsPerBot) + 1;
            for (let c = 0; c < howManyCards; c++) {
                this.botQueue.push(botId);
            }
        }

        this.botQueue.sort(() => Math.random() - 0.5);
        this.botInjectIndex = 0;
    }

    _processBotQueue() {
        if (!this.botQueue || this.botInjectIndex >= this.botQueue.length) return;

        let steps = Math.floor(Math.random() * 3) + 1;
        let changed = false;

        for (let s = 0; s < steps && this.botInjectIndex < this.botQueue.length; s++) {
            const botId = this.botQueue[this.botInjectIndex++];

            let availableCartels = [];
            for (let i = 1; i <= CARTEL_COUNT; i++) {
                if (!this.cartels[i]) availableCartels.push(i);
            }

            if (availableCartels.length === 0) break;

            const chosenCartel = availableCartels[Math.floor(Math.random() * availableCartels.length)];

            if (chosenCartel >= 1 && chosenCartel <= CARTEL_COUNT) {
                const botExistingCount = Object.values(this.cartels).filter(u => u === botId).length;
                if (botExistingCount < MAX_SELECTION) {
                    this.cartels[chosenCartel] = botId;
                    changed = true;
                }
            }
        }

        if (changed) {
            this._seq++;
        }
    }

    async _do_lock(snapshot) {
        let rid = this.round_id;

        await this.wallet.begin_round(rid, snapshot);

        let realSnapshot = {};
        for (let [cartel, uid] of Object.entries(snapshot)) {
            if (!String(uid).startsWith('bot_')) {
                realSnapshot[cartel] = uid;
            }
        }

        let byUser = {};

        for (let [cartel, uid] of Object.entries(realSnapshot)) {
            if (!byUser[uid]) byUser[uid] = [];
            byUser[uid].push(Number(cartel));
        }

        let paid = {};
        this.restrictedUsers = new Set();

        for (let [uid, cartels] of Object.entries(byUser)) {
            let res = await this.wallet.charge(
                uid,
                cartels.length * TICKET_PRICE,
                rid,
                cartels.length
            );

            if (res !== null) {
                for (let c of cartels) paid[c] = uid;

                if (this.botSettings.restrictDepositedWin) {
                    const prof = await this.wallet.profile(uid);
                    if (prof && prof.has_deposited) {
                        this.restrictedUsers.add(String(uid));
                    }
                }
            } else {
                await this.wallet.refund(uid, rid);
            }
        }

        for (let [cartel, uid] of Object.entries(snapshot)) {
            if (String(uid).startsWith('bot_')) {
                paid[cartel] = uid;
            }
        }

        this.cartels = paid;

        try {
            await this.wallet.start_drawing(rid, paid);
        } catch (error) {
            console.error('Could not persist drawing round; refunding tickets:', error);
            let realPaidUids = [...new Set(Object.values(paid).filter(u => !String(u).startsWith('bot_')))];
            await this.wallet.cancel_round(rid, realPaidUids);
            this.cartels = {};
            this.phase = 'selection';
            this.phase_ends_at = Date.now() / 1000 + this.selection_seconds;
            this._seq++;
            return;
        }

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
        let nextIndex = this.drawn.length;
        let chosenNumber = this.draw_order[nextIndex];

        if (this.botSettings.restrictDepositedWin && this.restrictedUsers && this.restrictedUsers.size > 0) {
            let safeIndex = -1;

            for (let i = nextIndex; i < this.draw_order.length; i++) {
                let candidateNum = this.draw_order[i];
                let testSet = new Set(this.drawn);
                testSet.add(candidateNum);

                let makesRestrictedWin = false;

                for (let [cartel, uid] of Object.entries(this.cartels)) {
                    if (this.restrictedUsers.has(String(uid))) {
                        if (checkBingo(generateMatrix(Number(cartel)), testSet)) {
                            makesRestrictedWin = true;
                            break;
                        }
                    }
                }

                if (!makesRestrictedWin) {
                    safeIndex = i;
                    break;
                }
            }

            if (safeIndex !== -1) {
                chosenNumber = this.draw_order[safeIndex];
                this.draw_order[safeIndex] = this.draw_order[nextIndex];
                this.draw_order[nextIndex] = chosenNumber;
            } else {
                const nonRestrictedCartels = Object.entries(this.cartels)
                    .filter(([c, u]) => !this.restrictedUsers.has(String(u)))
                    .map(([c]) => Number(c));

                if (nonRestrictedCartels.length > 0) {
                    const luckyCartel = nonRestrictedCartels[Math.floor(Math.random() * nonRestrictedCartels.length)];
                    this._pending = ['win', [luckyCartel]];
                    this.phase = 'settling';
                    return;
                }
            }
        }

        let number = chosenNumber;
        this.drawn.push(number);
        this._seq++;

        let drawnSet = new Set(this.drawn);
        let winning = [];

        for (let [cartel, uid] of Object.entries(this.cartels)) {
            const cartelNum = Number(cartel);
            if (cartelNum >= 1 && cartelNum <= CARTEL_COUNT) {
                if (checkBingo(generateMatrix(cartelNum), drawnSet)) {
                    winning.push(cartelNum);
                }
            }
        }

        if (winning.length === 0 && this.drawn.length >= 25) {
            const botWinChance = Number(this.botSettings.botWinPercent) || 0;
            if (Math.random() * 100 < botWinChance) {
                const botCartels = Object.entries(this.cartels)
                    .filter(([c, u]) => String(u).startsWith('bot_') && Number(c) >= 1 && Number(c) <= CARTEL_COUNT)
                    .map(([c]) => Number(c));

                if (botCartels.length > 0) {
                    const chosenBotCartel = botCartels[Math.floor(Math.random() * botCartels.length)];
                    winning.push(chosenBotCartel);
                }
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
            let realWinnersList = [];

            for (let c of wins) {
                let uid = tickets[c];
                if (!String(uid).startsWith('bot_')) {
                    payouts[uid] = (payouts[uid] || 0) + share;
                }
                realWinnersList.push({ cartel: c, uid: uid });
            }

            let profiles = {};

            for (let uid of Object.keys(payouts)) {
                profiles[uid] = await this.wallet.profile(uid) || {};
            }

            if (Object.keys(payouts).length > 0) {
                await this.wallet.prepare_settlement(rid, payouts);
                await this.wallet.settle(rid, payouts);
            }

            this.winners = realWinnersList.map(w => {
                const isBot = String(w.uid).startsWith('bot_');
                let winnerName = 'Player';

                if (isBot) {
                    winnerName = this.botProfiles[w.uid]?.name || 'ተጫዋች';
                } else {
                    winnerName = profiles[w.uid]?.name || profiles[w.uid]?.username || 'Player';
                }

                return {
                    uid: w.uid,
                    cartel: Number(w.cartel),
                    prize: share,
                    name: winnerName
                };
            });

            this.no_winner = false;
        } else {
            let realUserIds = [...new Set(Object.entries(tickets).filter(([c, u]) => !String(u).startsWith('bot_')).map(([c, u]) => u))];
            await this.wallet.cancel_round(rid, realUserIds);

            this.winners = [];
            this.no_winner = true;
        }

        this.phase = 'result';
        this.phase_ends_at = Date.now() / 1000 + this.result_seconds;

        this._seq++;

        if (this.on_round_result) {
            let uniquePlayers = new Set(Object.values(tickets));

            this.on_round_result({
                round_id: rid,
                players: uniquePlayers.size,
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
