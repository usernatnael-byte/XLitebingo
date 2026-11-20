const path = require('path');
const fs = require('fs');
const http = require('http');
const express = require('express');
const cors = require('cors');
const { Server } = require('socket.io');

const { BalanceManager } = require('./balance');
const selection = require('./selection');
const { KenoRoom, AviatorRoom, BingoRoom } = require('./game_rooms');

function resolveHtmlPath() {
  const candidates = [
    path.join(__dirname, 'index.html'),
    path.join(__dirname, 'public', 'index.html'),
    path.join(__dirname, '..', 'index.html')
  ];
  return candidates.find((p) => fs.existsSync(p)) || null;
}

function createPlatformServer() {
  const app = express();
  const httpServer = http.createServer(app);

  app.use(cors());
  app.use(express.json({ limit: '2mb' }));

  const io = new Server(httpServer, {
    cors: { origin: '*', methods: ['GET', 'POST'] }
  });

  // 1. አንድ የጋራ ባላንስ ለሁሉም ጨዋታዎች (Keno, Aviator, Bingo)
  const sharedBalanceManager = new BalanceManager();

  // 2. የተለያዩ Game Room Logics
  const kenoRoom = new KenoRoom({ balanceOptions: {} });
  kenoRoom.balanceManager = sharedBalanceManager;

  const aviatorRoom = new AviatorRoom({ balanceManager: sharedBalanceManager });
  const bingoRoom = new BingoRoom({ balanceManager: sharedBalanceManager });

  kenoRoom.attachSocketIO(io);
  aviatorRoom.attachSocketIO(io);
  bingoRoom.attachSocketIO(io);

  kenoRoom.start();
  aviatorRoom.start();
  bingoRoom.start();

  const roomsMap = new Map([
    ['keno', kenoRoom],
    ['aviator', aviatorRoom],
    ['bingo', bingoRoom]
  ]);

  function getUnifiedState(playerId) {
    const uid = String(playerId || '').trim();
    const acc = sharedBalanceManager.ensureAccount(uid);
    return {
      serverConnected: true,
      player: sharedBalanceManager.getSummary(acc.playerId),
      history: sharedBalanceManager.getHistory(acc.playerId, 50),
      rooms: {
        keno: kenoRoom.getSnapshot(acc.playerId),
        aviator: aviatorRoom.getSnapshot(acc.playerId),
        bingo: bingoRoom.getSnapshot(acc.playerId)
      }
    };
  }

  function emitBalanceToPlayer(playerId, balance) {
    for (const [sockId, boundUid] of socketToPlayer.entries()) {
      if (boundUid === String(playerId)) {
        io.to(sockId).emit('balance:update', { balance });
      }
    }
  }

  // REST Endpoints
  const router = express.Router();

  router.get('/health', (req, res) => {
    res.json({
      ok: true,
      rooms: ['keno', 'aviator', 'bingo'],
      connectedSockets: io.engine.clientsCount
    });
  });

  router.get('/state', (req, res) => {
    const playerId = String(req.query.playerId || req.get('X-Player-Id') || '');
    if (!playerId) {
      return res.status(400).json({ status: 'error', error: 'playerId is required' });
    }
    res.json({ status: 'success', ...getUnifiedState(playerId) });
  });

  router.post('/keno/bet', (req, res) => {
    const { playerId, displayName, picks, betAmount } = req.body || {};
    if (!playerId) return res.status(400).json({ status: 'error', error: 'playerId is required' });
    const result = kenoRoom.placeBet({ playerId, displayName, picks, betAmount });
    if (!result.ok) {
      return res.status(400).json({ status: 'error', error: result.error, balance: result.balance });
    }
    emitBalanceToPlayer(playerId, result.balance);
    res.json({ status: 'success', ...result });
  });

  router.post('/keno/autopick', (req, res) => {
    const count = Number(req.body?.count || 5);
    res.json({ status: 'success', picks: selection.autoPickNumbers(count) });
  });

  app.use('/api/platform', router);

  // Socket.IO Unified Session & Room Actions
  const socketToPlayer = new Map();

  io.on('connection', (socket) => {
    const authId = socket.handshake.auth?.playerId || socket.handshake.query?.playerId;
    if (!authId) {
      socket.emit('auth:required', { error: 'playerId is required to join rooms.' });
      socket.disconnect(true);
      return;
    }

    const uid = String(authId).trim();
    const displayName = String(socket.handshake.auth?.displayName || '').trim();
    sharedBalanceManager.ensureAccount(uid, displayName);
    socketToPlayer.set(socket.id, uid);

    socket.emit('platform:state', getUnifiedState(uid));

    socket.on('platform:sync', (_, ack) => {
      const pid = socketToPlayer.get(socket.id) || uid;
      const snap = getUnifiedState(pid);
      socket.emit('platform:state', snap);
      if (typeof ack === 'function') ack({ ok: true, state: snap });
    });

    socket.on('room:action', (payload = {}, ack) => {
      const pid = socketToPlayer.get(socket.id) || uid;
      const game = String(payload.game || '').toLowerCase();
      const room = roomsMap.get(game);

      if (!room) {
        if (typeof ack === 'function') ack({ ok: false, error: 'Invalid game room.' });
        return;
      }

      let res;
      if (game === 'keno' && payload.type === 'bet') {
        res = room.placeBet({
          playerId: pid,
          displayName: payload.displayName,
          picks: payload.picks,
          betAmount: payload.betAmount
        });
      } else if (typeof room.handleSocketAction === 'function') {
        res = room.handleSocketAction(pid, payload);
      } else {
        res = { ok: false, error: 'Action not supported in room.' };
      }

      if (res && typeof res.balance === 'number') {
        emitBalanceToPlayer(pid, res.balance);
      }

      if (typeof ack === 'function') ack(res);
    });

    socket.on('disconnect', () => {
      socketToPlayer.delete(socket.id);
    });
  });

  const htmlPath = resolveHtmlPath();
  if (htmlPath) {
    app.use(express.static(path.dirname(htmlPath)));
    app.get('/', (req, res) => res.sendFile(htmlPath));
  }

  return { app, httpServer, io, sharedBalanceManager, kenoRoom, aviatorRoom, bingoRoom };
}

if (require.main === module) {
  const port = Number(process.env.PORT || 3000);
  const { httpServer } = createPlatformServer();
  httpServer.listen(port, '0.0.0.0', () => {
    console.log(`Unified Game Server (Keno, Aviator, Bingo) running on port ${port}`);
  });
}

module.exports = { createPlatformServer };
