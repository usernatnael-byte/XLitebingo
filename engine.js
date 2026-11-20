const EventEmitter = require('events');
const { fisherYatesDraw, DRAW_COUNT, MIN_NUMBER, MAX_NUMBER } = require('./selection');
const { PHASES, KenoRound } = require('./round');

class KenoEngine extends EventEmitter {
  constructor(options = {}) {
    super();
    this.bettingDurationSec = Math.max(10, Number(options.bettingDurationSec || process.env.KENO_BETTING_SEC || 45));
    this.closedDurationSec = Math.max(1, Number(options.closedDurationSec || process.env.KENO_CLOSED_SEC || 3));
    this.drawBallIntervalMs = Math.max(200, Number(options.drawBallIntervalMs || process.env.KENO_DRAW_INTERVAL_MS || 750));
    this.settledDurationSec = Math.max(1, Number(options.settledDurationSec || process.env.KENO_SETTLED_SEC || 3));

    this.roundSeq = Number(options.initialRoundId || process.env.KENO_INITIAL_ROUND_ID || 263953);
    this.currentRound = null;

    this._timer = null;
    this._running = false;
    this._lastTickSec = -1;
    this._nextBallAt = 0;
    this._drawCompleteAt = 0;
  }

  _createNextRound() {
    const round = new KenoRound(this.roundSeq, {
      bettingDurationSec: this.bettingDurationSec,
      closedDurationSec: this.closedDurationSec,
      drawBallIntervalMs: this.drawBallIntervalMs,
      settledDurationSec: this.settledDurationSec
    });
    this.currentRound = round;
    this._lastTickSec = round.getTimeLeftSec();
    this._nextBallAt = 0;
    this._drawCompleteAt = 0;
    return round;
  }

  start() {
    if (this._running) return;
    this._running = true;
    const firstRound = this._createNextRound();
    this.emit('round:open', {
      roundId: firstRound.roundId,
      phase: firstRound.phase,
      timeLeft: firstRound.getTimeLeftSec(),
      bettingDurationSec: this.bettingDurationSec
    });
    this._timer = setInterval(() => this._step(), 100);
  }

  stop() {
    this._running = false;
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  }

  _step() {
    if (!this._running || !this.currentRound) return;
    const now = Date.now();
    const round = this.currentRound;

    if (round.phase === PHASES.BETTING_OPEN) {
      const timeLeft = round.getTimeLeftSec(now);
      if (timeLeft !== this._lastTickSec) {
        this._lastTickSec = timeLeft;
        this.emit('round:tick', { roundId: round.roundId, phase: round.phase, timeLeft });
      }
      if (now >= round.phaseEndsAt) {
        const drawn20 = fisherYatesDraw(DRAW_COUNT, MIN_NUMBER, MAX_NUMBER);
        round.lockBettingAndSetDraw(drawn20, now);
        this._lastTickSec = round.getTimeLeftSec(now);
        this.emit('round:closed', {
          roundId: round.roundId,
          phase: round.phase,
          timeLeft: this._lastTickSec,
          totalTickets: round.tickets.length
        });
      }
      return;
    }

    if (round.phase === PHASES.BETTING_CLOSED) {
      const timeLeft = round.getTimeLeftSec(now);
      if (timeLeft !== this._lastTickSec) {
        this._lastTickSec = timeLeft;
        this.emit('round:tick', { roundId: round.roundId, phase: round.phase, timeLeft });
      }
      if (now >= round.phaseEndsAt) {
        round.startDrawing(now);
        this._nextBallAt = now;
        this._drawCompleteAt = 0;
        this.emit('round:draw_start', { roundId: round.roundId, phase: round.phase, totalBalls: DRAW_COUNT });
      }
      return;
    }

    if (round.phase === PHASES.DRAWING) {
      if (round.revealedNumbers.length < DRAW_COUNT && now >= this._nextBallAt) {
        const ballEvent = round.revealNextBall();
        this._nextBallAt = now + this.drawBallIntervalMs;
        if (ballEvent) {
          this.emit('round:ball', { roundId: round.roundId, phase: round.phase, ...ballEvent });
        }
        if (round.revealedNumbers.length >= DRAW_COUNT) {
          this._drawCompleteAt = now + this.drawBallIntervalMs;
        }
        return;
      }

      if (round.revealedNumbers.length >= DRAW_COUNT && this._drawCompleteAt > 0 && now >= this._drawCompleteAt) {
        const tickets = round.settleRound(now);
        const resultRecord = round.toResultRecord();
        this.emit('round:settled', {
          roundId: round.roundId,
          phase: round.phase,
          drawnNumbers: [...round.drawnNumbers],
          tickets,
          resultRecord,
          totalPool: round.totalPool,
          totalPayout: round.totalPayout
        });
      }
      return;
    }

    if (round.phase === PHASES.SETTLED) {
      if (now >= round.phaseEndsAt) {
        this.roundSeq += 1;
        const nextRound = this._createNextRound();
        this.emit('round:open', {
          roundId: nextRound.roundId,
          phase: nextRound.phase,
          timeLeft: nextRound.getTimeLeftSec(),
          bettingDurationSec: this.bettingDurationSec
        });
      }
    }
  }
}

module.exports = { KenoEngine, PHASES };
