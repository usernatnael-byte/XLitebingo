const { roundCurrency } = require('./selection');

const DEFAULT_BALANCE = Number(process.env.DEFAULT_BALANCE_ETB || 171.84);
const MIN_BET = Math.max(1, Number(process.env.MIN_BET_ETB || 1));
const MAX_BET = Math.max(MIN_BET, Number(process.env.MAX_BET_ETB || 10000));

function maskPlayerId(playerId) {
  const raw = String(playerId || 'player').replace(/[^a-zA-Z0-9_-]/g, '');
  if (raw.length <= 2) return `${raw[0] || 'p'}***`;
  return `${raw[0]}***${raw[raw.length - 1]}`;
}

class BalanceManager {
  constructor(options = {}) {
    this.defaultBalance = Number.isFinite(options.defaultBalance)
      ? options.defaultBalance
      : DEFAULT_BALANCE;
    this.minBet = Number.isFinite(options.minBet) ? options.minBet : MIN_BET;
    this.maxBet = Number.isFinite(options.maxBet) ? options.maxBet : MAX_BET;

    this.accounts = new Map();
    this.processedOps = new Set();
    this.leaders = [
      { id: 'f***b', playerId: 'seed_1', bet: 800, winAmount: 30000, roundId: 263940, createdAt: Date.now() - 600000 },
      { id: 'd***j', playerId: 'seed_2', bet: 1000, winAmount: 30000, roundId: 263932, createdAt: Date.now() - 900000 },
      { id: 'a***h', playerId: 'seed_3', bet: 600, winAmount: 30000, roundId: 263925, createdAt: Date.now() - 1200000 }
    ];
  }

  ensureAccount(playerId, displayName = '') {
    const uid = String(playerId || '').trim() || `guest_${Date.now()}`;
    let acc = this.accounts.get(uid);
    if (!acc) {
      acc = {
        playerId: uid,
        maskedId: maskPlayerId(uid),
        displayName: String(displayName || '').trim() || maskPlayerId(uid),
        balance: roundCurrency(this.defaultBalance),
        totalWagered: 0,
        totalWon: 0,
        ticketsCount: 0,
        history: [],
        transactions: [],
        updatedAt: Date.now()
      };
      this.accounts.set(uid, acc);
    } else if (displayName && displayName.trim()) {
      acc.displayName = displayName.trim();
    }
    return acc;
  }

  getBalance(playerId) {
    return this.ensureAccount(playerId).balance;
  }

  getSummary(playerId) {
    const acc = this.ensureAccount(playerId);
    return {
      playerId: acc.playerId,
      maskedId: acc.maskedId,
      displayName: acc.displayName,
      balance: acc.balance,
      totalWagered: acc.totalWagered,
      totalWon: acc.totalWon,
      ticketsCount: acc.ticketsCount
    };
  }

  placeBetDebit({ playerId, amount, roundId, ticketId, displayName }) {
    const acc = this.ensureAccount(playerId, displayName);
    const bet = roundCurrency(amount);

    if (!Number.isFinite(bet) || bet < this.minBet || bet > this.maxBet) {
      return {
        ok: false,
        error: `Bet amount must be between ${this.minBet.toFixed(2)} and ${this.maxBet.toFixed(2)} ETB.`,
        balance: acc.balance
      };
    }

    const opKey = `debit:${ticketId}`;
    if (this.processedOps.has(opKey)) {
      return { ok: true, idempotent: true, balance: acc.balance, bet };
    }

    if (acc.balance < bet) {
      return { ok: false, error: 'Insufficient balance!', balance: acc.balance };
    }

    acc.balance = roundCurrency(acc.balance - bet);
    acc.totalWagered = roundCurrency(acc.totalWagered + bet);
    acc.ticketsCount += 1;
    acc.updatedAt = Date.now();
    acc.transactions.unshift({
      id: opKey,
      type: 'BET',
      roundId,
      ticketId,
      amount: -bet,
      balanceAfter: acc.balance,
      createdAt: acc.updatedAt
    });
    if (acc.transactions.length > 200) acc.transactions.length = 200;

    this.processedOps.add(opKey);
    return { ok: true, balance: acc.balance, bet, account: acc };
  }

  refundBet({ playerId, amount, roundId, ticketId }) {
    const acc = this.ensureAccount(playerId);
    const bet = roundCurrency(amount);
    const opKey = `refund:${ticketId}`;
    if (this.processedOps.has(opKey)) {
      return { ok: true, idempotent: true, balance: acc.balance };
    }

    acc.balance = roundCurrency(acc.balance + bet);
    acc.totalWagered = roundCurrency(Math.max(0, acc.totalWagered - bet));
    acc.ticketsCount = Math.max(0, acc.ticketsCount - 1);
    acc.updatedAt = Date.now();
    acc.transactions.unshift({
      id: opKey,
      type: 'REFUND',
      roundId,
      ticketId,
      amount: bet,
      balanceAfter: acc.balance,
      createdAt: acc.updatedAt
    });
    if (acc.transactions.length > 200) acc.transactions.length = 200;

    this.processedOps.add(opKey);
    return { ok: true, balance: acc.balance };
  }

  settleTicketResult({ playerId, roundId, ticketId, picks, hits, bet, winAmount }) {
    const acc = this.ensureAccount(playerId);
    const payout = roundCurrency(winAmount);
    const opKey = `settle:${ticketId}`;

    if (this.processedOps.has(opKey)) {
      return { ok: true, idempotent: true, balance: acc.balance };
    }

    if (payout > 0) {
      acc.balance = roundCurrency(acc.balance + payout);
      acc.totalWon = roundCurrency(acc.totalWon + payout);
      acc.transactions.unshift({
        id: opKey,
        type: 'WIN',
        roundId,
        ticketId,
        amount: payout,
        balanceAfter: acc.balance,
        createdAt: Date.now()
      });
      if (acc.transactions.length > 200) acc.transactions.length = 200;

      this.recordLeaderboardEntry({
        id: acc.maskedId,
        playerId: acc.playerId,
        bet: roundCurrency(bet),
        winAmount: payout,
        roundId,
        createdAt: Date.now()
      });
    }

    acc.history.unshift({
      id: roundId,
      ticketId,
      picks: [...picks],
      hits: [...hits],
      bet: roundCurrency(bet),
      win: payout,
      settledAt: Date.now()
    });
    if (acc.history.length > 100) acc.history.length = 100;

    acc.updatedAt = Date.now();
    this.processedOps.add(opKey);

    return { ok: true, balance: acc.balance, win: payout };
  }

  topUp(playerId, amount = 100) {
    const acc = this.ensureAccount(playerId);
    const credit = roundCurrency(Math.min(50000, Math.max(1, Number(amount) || 100)));
    acc.balance = roundCurrency(acc.balance + credit);
    acc.updatedAt = Date.now();
    acc.transactions.unshift({
      id: `topup:${Date.now()}`,
      type: 'TOPUP',
      amount: credit,
      balanceAfter: acc.balance,
      createdAt: acc.updatedAt
    });
    if (acc.transactions.length > 200) acc.transactions.length = 200;
    return { ok: true, balance: acc.balance, added: credit };
  }

  recordLeaderboardEntry(entry) {
    this.leaders.push(entry);
    this.leaders.sort((a, b) => b.winAmount - a.winAmount || a.bet - b.bet || b.createdAt - a.createdAt);
    if (this.leaders.length > 30) this.leaders.length = 30;
  }

  getHistory(playerId, limit = 40) {
    return this.ensureAccount(playerId).history.slice(0, limit);
  }

  getLeaders(limit = 20) {
    return this.leaders.slice(0, limit).map((item, idx) => ({
      rank: idx + 1,
      id: item.id,
      bet: item.bet,
      win: `${Math.round(item.winAmount)} ETB`,
      winAmount: item.winAmount,
      roundId: item.roundId
    }));
  }
}

module.exports = {
  BalanceManager,
  maskPlayerId,
  DEFAULT_BALANCE,
  MIN_BET,
  MAX_BET
};
