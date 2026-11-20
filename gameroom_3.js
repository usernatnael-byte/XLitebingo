const selection = require('./selection');
const { BalanceManager } = require('./balance');
const { KenoEngine, PHASES } = require('./engine');

class GameRoom {
  constructor(options = {}) {
    this.roomId = options.roomId || 'fast-keno-main';
    this.maxHistoryResults = Number(options.maxHistoryResults || 100);

    this.balanceManager = new BalanceManager(options.balanceOptions || {});
    this.pastResults = this._seedInitialResults(options.initialRoundId || 263953);

    this.engine = new KenoEngine({
      initialRoundId: options.initialRoundId || 263953,
      bettingDurationSec: options.bettingDurationSec,
      closedDurationSec: options.closedDurationSec,
      drawBallIntervalMs: options.drawBallIntervalMs,
      settledDurationSec: options.settledDurationSec
    });

    this.io = null;
    this.socketPlayers = new Map();
    this.allBetsCount = 33465;

    this._bindEngineEvents();
  }

  _seedInitialResults(nextRoundId) {
    const seeded = [];
    const now = Date.now();
    for (let i = 1; i <= 24; i++) {
      const ts = new Date(now - i * 65000);
      const hh = String(ts.getHours()).padStart(2, '0');
      const mm = String(ts.getMinutes()).padStart(2, '0');
      const ss = String(ts.getSeconds()).padStart(2, '0');
      seeded.push({
        id: nextRoundId - i,
        time: `${hh}:${mm}:${ss}`,
        nums: selection.fisherYatesDraw(selection.DRAW_COUNT, selection.MIN_NUMBER, selection.MAX_NUMBER)
      });
    }
    return seeded;
  }

  _getStatsBundle() {
    return selection.computeStatistics(this.pastResults, this.maxHistoryResults);
  }

  _emitToPlayer(playerId, eventName, payload) {
    if (!this.io) return;
    const uid = String(playerId);
    for (const [socketId, boundUid] of this.socketPlayers.entries()) {
      if (boundUid === uid) this.io.to(socketId).emit(eventName, payload);
    }
  }

  _bindEngineEvents() {
    this.engine.on('round:open', (data) => {
      if (!this.io) return;
      this.io.to(this.roomId).emit('round:open', { ...data, allBetsCount: this.allBetsCount });
    });

    this.engine.on('round:tick', (data) => {
      if (this.io) this.io.to(this.roomId).emit('round:tick', data);
    });

    this.engine.on('round:closed', (data) => {
      if (this.io) this.io.to(this.roomId).emit('round:closed', data);
    });

    this.engine.on('round:draw_start', (data) => {
      if (this.io) this.io.to(this.roomId).emit('round:draw_start', data);
    });

    this.engine.on('round:ball', (data) => {
      if (this.io) this.io.to(this.roomId).emit('round:ball', data);
    });

    this.engine.on('round:settled', (data) => {
      const affectedPlayers = new Set();
      for (const t of data.tickets) {
        this.balanceManager.settleTicketResult({
          playerId: t.playerId,
          roundId: t.roundId,
          ticketId: t.ticketId,
          picks: t.picks,
          hits: t.hits,
          bet: t.bet,
          winAmount: t.win
        });
        affectedPlayers.add(t.playerId);
      }

      this.pastResults.unshift(data.resultRecord);
      if (this.pastResults.length > this.maxHistoryResults) {
        this.pastResults.length = this.maxHistoryResults;
      }

      const statsBundle = this._getStatsBundle();
      const leaders = this.balanceManager.getLeaders(20);

      for (const pid of affectedPlayers) {
        const round = this.engine.currentRound;
        this._emitToPlayer(pid, 'player:settled', {
          roundId: data.roundId,
          balance: this.balanceManager.getBalance(pid),
          tickets: round ? round.getPlayerTickets(pid) : [],
          history: this.balanceManager.getHistory(pid, 40)
        });
      }

      if (this.io) {
        this.io.to(this.roomId).emit('round:settled', {
          roundId: data.roundId,
          phase: data.phase,
          drawnNumbers: data.drawnNumbers,
          resultRecord: data.resultRecord,
          pastResults: this.pastResults.slice(0, 30),
          hotNumbers: statsBundle.hotNumbers,
          coldNumbers: statsBundle.coldNumbers,
          stats: statsBundle.stats,
          roundsAnalyzed: statsBundle.roundsAnalyzed,
          leaders
        });
      }
    });
  }

  attachSocketIO(io) {
    this.io = io;
    io.on('connection', (socket) => {
      socket.join(this.roomId);
      const authPlayerId = socket.handshake.auth?.playerId || socket.handshake.query?.playerId;
      const authName = socket.handshake.auth?.displayName || '';
      const boundId = String(authPlayerId || `guest_${socket.id.slice(0, 8)}`);

      this.balanceManager.ensureAccount(boundId, authName);
      this.socketPlayers.set(socket.id, boundId);
      socket.emit('room:state', this.getSnapshot(boundId));

      socket.on('disconnect', () => {
        this.socketPlayers.delete(socket.id);
      });
    });
  }

  placeBet({ playerId, displayName, picks, betAmount }) {
    const round = this.engine.currentRound;
    if (!round || round.phase !== PHASES.BETTING_OPEN) {
      return { ok: false, error: 'Betting is closed for this round. Wait for next round.' };
    }

    const validation = selection.validatePicks(picks);
    if (!validation.valid) {
      return { ok: false, error: validation.error };
    }

    const acc = this.balanceManager.ensureAccount(playerId, displayName);
    const pendingTicketId = `t_${round.roundId}_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;

    const debit = this.balanceManager.placeBetDebit({
      playerId: acc.playerId,
      displayName: acc.displayName,
      amount: betAmount,
      roundId: round.roundId,
      ticketId: pendingTicketId
    });

    if (!debit.ok) {
      return { ok: false, error: debit.error, balance: debit.balance };
    }

    const added = round.addTicket({
      playerId: acc.playerId,
      maskedId: acc.maskedId,
      picks: validation.picks,
      bet: debit.bet
    });

    if (!added.ok) {
      this.balanceManager.refundBet({
        playerId: acc.playerId,
        amount: debit.bet,
        roundId: round.roundId,
        ticketId: pendingTicketId
      });
      return { ok: false, error: added.error, balance: this.balanceManager.getBalance(acc.playerId) };
    }

    this.allBetsCount += 1;
    const playerTickets = round.getPlayerTickets(acc.playerId);

    this._emitToPlayer(acc.playerId, 'balance:update', {
      balance: debit.balance,
      tickets: playerTickets
    });

    return {
      ok: true,
      ticket: added.ticket,
      tickets: playerTickets,
      balance: debit.balance,
      allBetsCount: this.allBetsCount
    };
  }

  getSnapshot(playerId) {
    const round = this.engine.currentRound;
    const acc = this.balanceManager.ensureAccount(playerId);
    const statsBundle = this._getStatsBundle();

    return {
      roomId: this.roomId,
      serverTime: Date.now(),
      roundId: round ? round.roundId : this.engine.roundSeq,
      phase: round ? round.phase : PHASES.BETTING_OPEN,
      timeLeft: round ? round.getTimeLeftSec() : this.engine.bettingDurationSec,
      bettingDurationSec: this.engine.bettingDurationSec,
      drawCount: selection.DRAW_COUNT,
      maxPicks: selection.MAX_PICKS,
      minBet: this.balanceManager.minBet,
      maxBet: this.balanceManager.maxBet,
      drawnSoFar: round ? [...round.revealedNumbers] : [],
      payoutTable: selection.PAYOUT_TABLE,
      allBetsCount: this.allBetsCount,
      hotNumbers: statsBundle.hotNumbers,
      coldNumbers: statsBundle.coldNumbers,
      stats: statsBundle.stats,
      roundsAnalyzed: statsBundle.roundsAnalyzed,
      pastResults: this.pastResults.slice(0, 30),
      leaders: this.balanceManager.getLeaders(20),
      publicTickets: round ? round.getPublicTickets(15) : [],
      player: {
        playerId: acc.playerId,
        maskedId: acc.maskedId,
        displayName: acc.displayName,
        balance: acc.balance,
        tickets: round ? round.getPlayerTickets(acc.playerId) : [],
        history: this.balanceManager.getHistory(acc.playerId, 40)
      }
    };
  }

  start() { this.engine.start(); }
  stop() { this.engine.stop(); }
}

module.exports = { GameRoom };
