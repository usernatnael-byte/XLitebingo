const crypto = require('crypto');
const { GameRoom: KenoRoom } = require('./gameroom_3');
const { roundCurrency } = require('./selection');

/**
 * 1. AVIATOR GAME ROOM
 * የራሱ multiplier loop (BETTING -> FLYING -> CRASHED) እና cashout logic አለው
 */
class AviatorRoom {
  constructor(options = {}) {
    this.roomId = 'aviator-main';
    this.balanceManager = options.balanceManager;
    this.io = null;

    this.roundId = Number(options.initialRoundId || 510001);
    this.phase = 'BETTING'; // BETTING | FLYING | CRASHED
    this.multiplier = 1.0;
    this.crashPoint = 1.0;
    this.timeLeft = 6;
    this.bets = new Map(); // playerId -> { betId, playerId, maskedId, amount, cashedOutAt, payout, status }
    this.history = [];

    this._timer = null;
    this._running = false;
  }

  attachSocketIO(io) {
    this.io = io;
  }

  _generateCrashPoint() {
    // 3% instant crash guard + exponential multiplier
    const r = crypto.randomInt(0, 10000) / 10000;
    if (r < 0.03) return 1.0;
    const raw = 0.97 / (1 - r);
    return Math.max(1.0, Math.min(100.0, Math.round(raw * 100) / 100));
  }

  _openBetting() {
    this.phase = 'BETTING';
    this.multiplier = 1.0;
    this.crashPoint = this._generateCrashPoint();
    this.timeLeft = 6;
    this.bets.clear();
    if (this.io) {
      this.io.emit('aviator:state', this.getSnapshot());
    }
  }

  _startFlight() {
    this.phase = 'FLYING';
    this.multiplier = 1.0;
    if (this.io) {
      this.io.emit('aviator:state', this.getSnapshot());
    }
  }

  _crashRound() {
    this.phase = 'CRASHED';
    for (const entry of this.bets.values()) {
      if (entry.status === 'ACTIVE') {
        entry.status = 'LOST';
        if (this.balanceManager) {
          this.balanceManager.settleTicketResult({
            playerId: entry.playerId,
            roundId: this.roundId,
            ticketId: entry.betId,
            picks: [],
            hits: [],
            bet: entry.amount,
            winAmount: 0
          });
        }
      }
    }
    this.history.unshift({
      roundId: this.roundId,
      crashPoint: this.crashPoint.toFixed(2),
      time: new Date().toISOString().slice(11, 19)
    });
    if (this.history.length > 30) this.history.length = 30;
    this.timeLeft = 3;
    if (this.io) {
      this.io.emit('aviator:state', this.getSnapshot());
    }
  }

  start() {
    if (this._running) return;
    this._running = true;
    this._openBetting();

    this._timer = setInterval(() => {
      if (!this._running) return;

      if (this.phase === 'BETTING') {
        this.timeLeft -= 0.2;
        if (this.timeLeft <= 0) {
          this._startFlight();
        }
        return;
      }

      if (this.phase === 'FLYING') {
        this.multiplier = Math.round((this.multiplier + 0.03) * 100) / 100;
        if (this.multiplier >= this.crashPoint) {
          this.multiplier = this.crashPoint;
          this._crashRound();
          return;
        }
        if (this.io) {
          this.io.emit('aviator:tick', {
            roundId: this.roundId,
            phase: this.phase,
            multiplier: this.multiplier
          });
        }
        return;
      }

      if (this.phase === 'CRASHED') {
        this.timeLeft -= 0.2;
        if (this.timeLeft <= 0) {
          this.roundId += 1;
          this._openBetting();
        }
      }
    }, 200);
  }

  stop() {
    this._running = false;
    if (this._timer) clearInterval(this._timer);
  }

  placeBet(playerId, amount, displayName = '') {
    if (!this.balanceManager) return { ok: false, error: 'Balance manager unavailable.' };
    if (this.phase !== 'BETTING') return { ok: false, error: 'Aviator betting is closed for this flight.' };
    if (this.bets.has(String(playerId))) return { ok: false, error: 'Already placed bet in this round.' };

    const betId = `av_${this.roundId}_${crypto.randomBytes(3).toString('hex')}`;
    const debit = this.balanceManager.placeBetDebit({
      playerId,
      amount,
      roundId: this.roundId,
      ticketId: betId,
      displayName
    });
    if (!debit.ok) return debit;

    const acc = this.balanceManager.ensureAccount(playerId, displayName);
    const entry = {
      betId,
      playerId: String(playerId),
      maskedId: acc.maskedId,
      amount: debit.bet,
      cashedOutAt: null,
      payout: 0,
      status: 'ACTIVE'
    };
    this.bets.set(String(playerId), entry);

    return { ok: true, bet: entry, balance: debit.balance };
  }

  cashOut(playerId) {
    if (this.phase !== 'FLYING') return { ok: false, error: 'Flight is not active.' };
    const entry = this.bets.get(String(playerId));
    if (!entry || entry.status !== 'ACTIVE') return { ok: false, error: 'No active bet to cash out.' };

    const winAmount = roundCurrency(entry.amount * this.multiplier);
    entry.status = 'CASHED_OUT';
    entry.cashedOutAt = this.multiplier;
    entry.payout = winAmount;

    const settled = this.balanceManager.settleTicketResult({
      playerId: entry.playerId,
      roundId: this.roundId,
      ticketId: `${entry.betId}:cashout`,
      picks: [],
      hits: [],
      bet: entry.amount,
      winAmount
    });

    return {
      ok: true,
      cashedOutAt: this.multiplier,
      winAmount,
      balance: settled.balance
    };
  }

  handleSocketAction(playerId, payload = {}) {
    if (payload.type === 'bet') {
      return this.placeBet(playerId, payload.betAmount, payload.displayName);
    }
    if (payload.type === 'cashout') {
      return this.cashOut(playerId);
    }
    return { ok: false, error: 'Unknown aviator action.' };
  }

  getSnapshot(playerId = '') {
    const myBet = playerId ? this.bets.get(String(playerId)) || null : null;
    return {
      roomId: this.roomId,
      roundId: this.roundId,
      phase: this.phase,
      multiplier: this.multiplier,
      timeLeft: Math.max(0, Math.ceil(this.timeLeft)),
      myBet,
      history: this.history.slice(0, 20)
    };
  }
}

/**
 * 2. BINGO GAME ROOM
 * የራሱ cartela selection፣ number calling (1-75) እና bingo line check logic አለው
 */
class BingoRoom {
  constructor(options = {}) {
    this.roomId = 'bingo-main';
    this.balanceManager = options.balanceManager;
    this.io = null;

    this.roundId = Number(options.initialRoundId || 810001);
    this.phase = 'LOBBY'; // LOBBY | CALLING | ENDED
    this.timeLeft = 10;
    this.calledNumbers = [];
    this.playerCards = new Map(); // playerId -> { cardId, playerId, bet, numbers: number[], status }
    this.winners = [];

    this._timer = null;
    this._running = false;
  }

  attachSocketIO(io) {
    this.io = io;
  }

  _generateCartela(cartelaNum) {
    const seed = Number(cartelaNum) || crypto.randomInt(1, 500);
    const nums = [];
    for (let i = 0; i < 25; i++) {
      if (i === 12) {
        nums.push(0); // FREE center
      } else {
        nums.push(((seed * 7 + i * 3) % 75) + 1);
      }
    }
    return nums;
  }

  _checkBingoWin(numbers, calledSet) {
    calledSet.add(0);
    // 5 rows, 5 cols, 2 diagonals
    for (let r = 0; r < 5; r++) {
      if ([0, 1, 2, 3, 4].every((c) => calledSet.has(numbers[r * 5 + c]))) return true;
    }
    for (let c = 0; c < 5; c++) {
      if ([0, 1, 2, 3, 4].every((r) => calledSet.has(numbers[r * 5 + c]))) return true;
    }
    if ([0, 6, 12, 18, 24].every((idx) => calledSet.has(numbers[idx]))) return true;
    if ([4, 8, 12, 16, 20].every((idx) => calledSet.has(numbers[idx]))) return true;
    return false;
  }

  _openLobby() {
    this.phase = 'LOBBY';
    this.timeLeft = 10;
    this.calledNumbers = [];
    this.playerCards.clear();
    this.winners = [];
    if (this.io) this.io.emit('bingo:state', this.getSnapshot());
  }

  _startCalling() {
    this.phase = 'CALLING';
    this.calledNumbers = [];
    if (this.io) this.io.emit('bingo:state', this.getSnapshot());
  }

  _endRound() {
    this.phase = 'ENDED';
    this.timeLeft = 4;
    for (const card of this.playerCards.values()) {
      if (card.status === 'PLAYING') {
        card.status = 'LOST';
        if (this.balanceManager) {
          this.balanceManager.settleTicketResult({
            playerId: card.playerId,
            roundId: this.roundId,
            ticketId: card.cardId,
            picks: card.numbers,
            hits: [],
            bet: card.bet,
            winAmount: 0
          });
        }
      }
    }
    if (this.io) this.io.emit('bingo:state', this.getSnapshot());
  }

  start() {
    if (this._running) return;
    this._running = true;
    this._openLobby();

    const poolBase = Array.from({ length: 75 }, (_, i) => i + 1);

    this._timer = setInterval(() => {
      if (!this._running) return;

      if (this.phase === 'LOBBY') {
        this.timeLeft -= 1;
        if (this.timeLeft <= 0) {
          this._startCalling();
        }
        return;
      }

      if (this.phase === 'CALLING') {
        const remaining = poolBase.filter((n) => !this.calledNumbers.includes(n));
        if (remaining.length === 0 || this.winners.length > 0) {
          this._endRound();
          return;
        }
        const picked = remaining[crypto.randomInt(0, remaining.length)];
        this.calledNumbers.push(picked);
        const calledSet = new Set(this.calledNumbers);

        for (const card of this.playerCards.values()) {
          if (card.status === 'PLAYING' && this._checkBingoWin(card.numbers, calledSet)) {
            const winAmount = roundCurrency(card.bet * 3.5);
            card.status = 'WON';
            this.winners.push({
              playerId: card.playerId,
              cardId: card.cardId,
              winAmount
            });
            if (this.balanceManager) {
              this.balanceManager.settleTicketResult({
                playerId: card.playerId,
                roundId: this.roundId,
                ticketId: card.cardId,
                picks: card.numbers,
                hits: [...this.calledNumbers],
                bet: card.bet,
                winAmount
              });
            }
          }
        }

        if (this.io) {
          this.io.emit('bingo:call', {
            roundId: this.roundId,
            number: picked,
            calledNumbers: [...this.calledNumbers],
            winners: [...this.winners]
          });
        }
        return;
      }

      if (this.phase === 'ENDED') {
        this.timeLeft -= 1;
        if (this.timeLeft <= 0) {
          this.roundId += 1;
          this._openLobby();
        }
      }
    }, 1000);
  }

  stop() {
    this._running = false;
    if (this._timer) clearInterval(this._timer);
  }

  joinWithCartela(playerId, cartelaNum, betAmount, displayName = '') {
    if (!this.balanceManager) return { ok: false, error: 'Balance manager unavailable.' };
    if (this.phase !== 'LOBBY') return { ok: false, error: 'Bingo round already started. Wait for next lobby.' };
    if (this.playerCards.has(String(playerId))) return { ok: false, error: 'Cartela already joined for this round.' };

    const cardId = `bg_${this.roundId}_${crypto.randomBytes(3).toString('hex')}`;
    const debit = this.balanceManager.placeBetDebit({
      playerId,
      amount: betAmount,
      roundId: this.roundId,
      ticketId: cardId,
      displayName
    });
    if (!debit.ok) return debit;

    const card = {
      cardId,
      cartelaNum: Number(cartelaNum) || 1,
      playerId: String(playerId),
      bet: debit.bet,
      numbers: this._generateCartela(cartelaNum),
      status: 'PLAYING'
    };
    this.playerCards.set(String(playerId), card);

    return { ok: true, card, balance: debit.balance };
  }

  handleSocketAction(playerId, payload = {}) {
    if (payload.type === 'join') {
      return this.joinWithCartela(playerId, payload.cartelaNum, payload.betAmount, payload.displayName);
    }
    return { ok: false, error: 'Unknown bingo action.' };
  }

  getSnapshot(playerId = '') {
    return {
      roomId: this.roomId,
      roundId: this.roundId,
      phase: this.phase,
      timeLeft: Math.max(0, Math.ceil(this.timeLeft)),
      calledNumbers: [...this.calledNumbers],
      winners: [...this.winners],
      myCard: playerId ? this.playerCards.get(String(playerId)) || null : null
    };
  }
}

module.exports = {
  KenoRoom,
  AviatorRoom,
  BingoRoom
};
