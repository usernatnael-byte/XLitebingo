const crypto = require('crypto');
const { evaluateTicket, roundCurrency } = require('./selection');

const PHASES = {
  BETTING_OPEN: 'BETTING_OPEN',
  BETTING_CLOSED: 'BETTING_CLOSED',
  DRAWING: 'DRAWING',
  SETTLED: 'SETTLED'
};

class KenoRound {
  constructor(roundId, config = {}) {
    this.roundId = Number(roundId);
    this.phase = PHASES.BETTING_OPEN;
    this.startedAt = Date.now();

    this.bettingDurationSec = Number(config.bettingDurationSec || 45);
    this.closedDurationSec = Number(config.closedDurationSec || 3);
    this.drawBallIntervalMs = Number(config.drawBallIntervalMs || 750);
    this.settledDurationSec = Number(config.settledDurationSec || 3);

    this.phaseEndsAt = this.startedAt + this.bettingDurationSec * 1000;

    this.tickets = [];
    this.drawnNumbers = [];
    this.revealedNumbers = [];
    this.settledAt = null;
    this.totalPool = 0;
    this.totalPayout = 0;
  }

  getTimeLeftSec(now = Date.now()) {
    return Math.max(0, Math.ceil((this.phaseEndsAt - now) / 1000));
  }

  addTicket({ playerId, maskedId, picks, bet }) {
    if (this.phase !== PHASES.BETTING_OPEN) {
      return { ok: false, error: 'Betting is closed for this round.' };
    }

    const ticket = {
      ticketId: `t_${this.roundId}_${crypto.randomBytes(4).toString('hex')}`,
      roundId: this.roundId,
      playerId: String(playerId),
      maskedId: String(maskedId || 'p***r'),
      picks: [...picks],
      bet: roundCurrency(bet),
      hits: [],
      hitCount: 0,
      multiplier: 0,
      win: 0,
      status: 'WAITING',
      createdAt: Date.now()
    };

    this.tickets.push(ticket);
    this.totalPool = roundCurrency(this.totalPool + ticket.bet);
    return { ok: true, ticket };
  }

  lockBettingAndSetDraw(drawnNumbers, now = Date.now()) {
    this.phase = PHASES.BETTING_CLOSED;
    this.drawnNumbers = [...drawnNumbers];
    this.revealedNumbers = [];
    this.phaseEndsAt = now + this.closedDurationSec * 1000;
    for (const t of this.tickets) t.status = 'LOCKED';
  }

  startDrawing(now = Date.now()) {
    this.phase = PHASES.DRAWING;
    this.drawingStartedAt = now;
    this.phaseEndsAt = now + this.drawnNumbers.length * this.drawBallIntervalMs;
  }

  revealNextBall() {
    const nextIndex = this.revealedNumbers.length;
    if (nextIndex >= this.drawnNumbers.length) return null;

    const num = this.drawnNumbers[nextIndex];
    this.revealedNumbers.push(num);

    const drawnSet = new Set(this.revealedNumbers);
    for (const t of this.tickets) {
      t.hits = t.picks.filter((n) => drawnSet.has(n));
      t.hitCount = t.hits.length;
      t.status = 'DRAWING';
    }

    return {
      ballIndex: nextIndex + 1,
      totalBalls: this.drawnNumbers.length,
      number: num,
      drawnSoFar: [...this.revealedNumbers]
    };
  }

  settleRound(now = Date.now()) {
    this.phase = PHASES.SETTLED;
    this.settledAt = now;
    this.phaseEndsAt = now + this.settledDurationSec * 1000;
    this.totalPayout = 0;

    for (const t of this.tickets) {
      const evaluation = evaluateTicket(t.picks, this.drawnNumbers, t.bet);
      t.hits = evaluation.hits;
      t.hitCount = evaluation.hitCount;
      t.multiplier = evaluation.multiplier;
      t.win = evaluation.winAmount;
      t.status = evaluation.won ? 'WON' : 'LOST';
      this.totalPayout = roundCurrency(this.totalPayout + t.win);
    }

    return this.tickets;
  }

  getPlayerTickets(playerId) {
    const uid = String(playerId || '');
    const drawnSet = new Set(this.revealedNumbers);

    return this.tickets
      .filter((t) => t.playerId === uid)
      .map((t) => ({
        ticketId: t.ticketId,
        roundId: t.roundId,
        picks: [...t.picks],
        bet: t.bet,
        hits: t.picks.filter((n) => drawnSet.has(n)),
        hitCount: t.hits.length,
        multiplier: this.phase === PHASES.SETTLED ? t.multiplier : 0,
        win: this.phase === PHASES.SETTLED ? t.win : 0,
        status: t.status
      }));
  }

  getPublicTickets(limit = 20) {
    return this.tickets.slice(-limit).reverse().map((t) => ({
      ticketId: t.ticketId,
      user: t.maskedId,
      picks: [...t.picks],
      bet: t.bet,
      win: this.phase === PHASES.SETTLED ? t.win : 0,
      status: t.status
    }));
  }

  toResultRecord() {
    const date = new Date(this.settledAt || Date.now());
    const hh = String(date.getHours()).padStart(2, '0');
    const mm = String(date.getMinutes()).padStart(2, '0');
    const ss = String(date.getSeconds()).padStart(2, '0');
    return { id: this.roundId, time: `${hh}:${mm}:${ss}`, nums: [...this.drawnNumbers] };
  }
}

module.exports = { PHASES, KenoRound };
