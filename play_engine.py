import secrets
import threading
import time
import traceback
from collections import defaultdict
from game_engine import CARTEL_COUNT, BALLS, PRIZE_PER_CARTEL, generate_matrix, check_bingo, _mask_phone

class PlayEngine:
    def __init__(self, wallet, min_players=2, selection_seconds=30, draw_interval=2.0, result_seconds=10):
        self.wallet = wallet
        self.min_players = max(1, int(min_players))
        self.selection_seconds = selection_seconds
        self.draw_interval = draw_interval
        self.result_seconds = result_seconds
        self.rng = secrets.SystemRandom()

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._seq = 0
        self.on_round_result = None

        with self._lock:
            self._new_round()

    def start(self):
        self._thread = threading.Thread(target=self._run_loop, name="play-engine", daemon=True)
        self._thread.start()
        print("🚀 PlayEngine Started Successfully!")

    def stop(self):
        self._stop.set()

    def _run_loop(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                traceback.print_exc()
            time.sleep(0.5)

    def _new_round(self):
        now = time.time()
        self.round_id = f"r{int(now * 1000)}"
        self.phase = "selection"
        self.phase_ends_at = now + self.selection_seconds
        self.cartels = {}

        # አውቶማቲክ ቦት 2 ካርቴል እንዲይዝ ማድረግ
        try:
            bot_cartels = self.rng.sample(range(1, CARTEL_COUNT + 1), 2)
            for c in bot_cartels:
                self.cartels[c] = "bot_player"
        except Exception:
            pass

        self.draw_order = []
        self.drawn = []
        self.next_draw_at = 0
        self.winners = []
        self.no_winner = False
        self._seq += 1

    def pick(self, uid, cartel):
        uid = str(uid)
        if not isinstance(cartel, int) or not 1 <= cartel <= CARTEL_COUNT:
            return False, "invalid"

        with self._lock:
            if self.phase != "selection":
                return False, "phase"
            if self.cartels.get(cartel) == uid:
                return True, "ok"
            if self.cartels.get(cartel) is not None:
                return False, "taken"
            
            self.cartels[cartel] = uid
            self._seq += 1
            return True, "ok"

    def unpick(self, uid, cartel):
        uid = str(uid)
        with self._lock:
            if self.phase != "selection":
                return False, "phase"
            if self.cartels.get(cartel) == uid:
                del self.cartels[cartel]
                self._seq += 1
                return True, "ok"
            return False, "invalid"

    def get_state(self, uid):
        uid = str(uid)
        with self._lock:
            mine = sorted(c for c, u in self.cartels.items() if u == uid)
            winners = []
            if self.phase == "result":
                winners = [{
                    "name": w["name"], "phone": w["phone"], "cartel": w["cartel"],
                    "prize": w["prize"], "mine": w["uid"] == uid
                } for w in self.winners]

            return {
                "round_id": self.round_id,
                "seq": self._seq,
                "phase": self.phase,
                "server_time": time.time(),
                "phase_ends_at": self.phase_ends_at if self.phase in ("selection", "result") else None,
                "selection_seconds": self.selection_seconds,
                "result_seconds": self.result_seconds,
                "min_players": self.min_players,
                "players": len(set(self.cartels.values())),
                "taken": sorted(self.cartels),
                "my_cartels": mine,
                "pool": len(self.cartels) * PRIZE_PER_CARTEL,
                "drawn": list(self.drawn),
                "winners": winners,
                "no_winner": self.no_winner if self.phase == "result" else False,
            }

    def _tick(self):
        with self._lock:
            now = time.time()
            if self.phase == "selection":
                if now >= self.phase_ends_at:
                    # 30 ሰከንድ ሲሞላ ወደ ሎኪንግ እና ድሮይንግ phase መቀየር
                    self.phase = "drawing"
                    order = list(range(1, BALLS + 1))
                    self.rng.shuffle(order)
                    self.draw_order = order
                    self.drawn = []
                    self.next_draw_at = now + 1.0
                    self._seq += 1

            elif self.phase == "drawing":
                if now >= self.next_draw_at:
                    if len(self.drawn) < BALLS:
                        num = self.draw_order[len(self.drawn)]
                        self.drawn.append(num)
                        self._seq += 1
                        self.next_draw_at = now + self.draw_interval

                        # ቢንጎ መኖሩን ማረጋገጥ (Auto-win check)
                        drawn_set = set(self.drawn)
                        winning = [c for c in sorted(self.cartels) if check_bingo(generate_matrix(c), drawn_set)]
                        if winning:
                            self._handle_win(winning)
                    else:
                        self._handle_no_win()

            elif self.phase == "result":
                if now >= self.phase_ends_at:
                    self._new_round()

    def _handle_win(self, winning_cartels):
        pool = len(self.cartels) * PRIZE_PER_CARTEL
        share = round(pool / len(winning_cartels), 2)
        payouts = defaultdict(float)
        
        winners = []
        for c in winning_cartels:
            uid = self.cartels[c]
            if uid != "bot_player":
                payouts[uid] += share
            profile = self.wallet.profile(uid) or {}
            winners.append({
                "uid": uid, "cartel": c, "prize": share,
                "name": profile.get("name") or "Player",
                "username": profile.get("username"),
                "phone": _mask_phone(profile.get("phone"))
            })

        self.wallet.settle(self.round_id, dict(payouts))
        self.winners = winners
        self.no_winner = False
        self.phase = "result"
        self.phase_ends_at = time.time() + self.result_seconds
        self._seq += 1

    def _handle_no_win(self):
        self.winners = []
        self.no_winner = True
        self.phase = "result"
        self.phase_ends_at = time.time() + self.result_seconds
        self._seq += 1
