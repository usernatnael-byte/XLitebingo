import math
import secrets
import threading
import time
import traceback
from collections import defaultdict

TICKET_PRICE = 10
PRIZE_PER_CARTEL = 8      # 10 ETB paid, 8 ETB goes into the pool (20% house cut)[span_1](start_span)[span_1](end_span)
MAX_SELECTION = 4         # cartels per player per round[span_2](start_span)[span_2](end_span)
CARTEL_COUNT = 500
BALLS = 75


# ---------------------------------------------------------------- bingo cards

_matrix_cache = {}


def _seeded_random(seed):
    x = math.sin(seed) * 10000
    return x - math.floor(x)


def generate_matrix(ticket_id):
    cached = _matrix_cache.get(ticket_id)
    if cached is not None:
        return cached
    seed = ticket_id * 1573
    matrix = []
    for col in range(5):
        numbers = []
        low = col * 15 + 1
        while len(numbers) < 5:
            value = low + math.floor(_seeded_random(seed) * 15)
            seed += 1
            if value not in numbers:
                numbers.append(value)
        matrix.append(numbers)
    _matrix_cache[ticket_id] = matrix
    return matrix


def check_bingo(m, drawn):
    """m[col][row]; the centre square is free. drawn is a set of numbers.""[span_3](start_span)"[span_3](end_span)
    for r in range(5):
        if all(m[c][r] in drawn for c in range(5) if not (r == 2 and c == 2)):
            return True
    for c in range(5):
        if all(m[c][r] in drawn for r in range(5) if not (r == 2 and c == 2)):
            return True
    if all(m[i][i] in drawn for i in range(5) if i != 2):
        return True
    if all(m[4 - i][i] in drawn for i in range(5) if i != 2):
        return True
    return all(n in drawn for n in (m[0][0], m[4][0], m[0][4], m[4][4]))


def _mask_phone(phone):
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    return ("***" + digits[-4:]) if len(digits) >= 4 else ""


# --------------------------------------------------------------------- engine
class GameEngine:
    def __init__(self, wallet, min_players=2, selection_seconds=30, draw_interval=2.0,
                 result_seconds=10, first_draw_delay=3.0, clock=time.time, rng=None):
        self.wallet = wallet
        self.min_players = max(1, int(min_players))
        self.selection_seconds = selection_seconds
        self.draw_interval = draw_interval
        self.result_seconds = result_seconds
        self.first_draw_delay = first_draw_delay
        self.clock = clock
        self.rng = rng or secrets.SystemRandom()  

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._seq = 0
        self._retry_at = 0
        self.on_round_result = None   
        with self._lock:
            self._new_round()

    # -------------------------------------------------------------- lifecycle
    def start(self):
        try:
            refunded = self.wallet.recover_unsettled()
            if refunded:
                print(f"[engine] refunded {refunded} unfinished round(s) after restart")[span_4](start_span)[span_4](end_span)
        except Exception:
            traceback.print_exc()
        self._thread = threading.Thread(target=self._run, name="game-engine", daemon=True)
        self._thread.start()
        print(f"🎰 Game engine started (min players: {self.min_players})")[span_5](start_span)[span_5](end_span)

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                traceback.print_exc()
            self._stop.wait(0.2)

    # ------------------------------------------------------------ player API
    def pick(self, uid, cartel):
        """Returns (ok, code). Codes: ok, invalid, phase, taken, full, balance, error.""[span_6](start_span)"[span_6](end_span)
        uid = str(uid)
        if not isinstance(cartel, int) or isinstance(cartel, bool) or not 1 <= cartel <= CARTEL_COUNT:
            return False, "invalid"
        with self._lock:
            if self.phase != "selection":
                return False, "phase"
            owner = self.cartels.get(cartel)
            if owner == uid:
                return True, "ok"
            if owner is not None:
                return False, "taken"
            if sum(1 for u in self.cartels.values() if u == uid) >= MAX_SELECTION:
                return False, "full"
        try:                                   # database read happens outside the lock[span_7](start_span)[span_7](end_span)
            balance = float(self.wallet.get_balance(uid))
        except Exception:
            traceback.print_exc()
            return False, "error"
        with self._lock:
            if self.phase != "selection":
                return False, "phase"
            owner = self.cartels.get(cartel)
            if owner == uid:
                return True, "ok"
            if owner is not None:
                return False, "taken"
            mine = sum(1 for u in self.cartels.values() if u == uid)
            if mine >= MAX_SELECTION:
                return False, "full"
            if balance + 1e-9 < (mine + 1) * TICKET_PRICE:
                return False, "balance"
            self.cartels[cartel] = uid
            self._seq += 1
            return True, "ok"

    def unpick(self, uid, cartel):
        uid = str(uid)
        with self._lock:
            if self.phase != "selection":
                return False, "phase"
            owner = self.cartels.get(cartel)
            if owner is None:
                return True, "ok"
            if owner != uid:
                return False, "invalid"
            del self.cartels[cartel]
            self._seq += 1
            return True, "ok"

    def get_state(self, uid):
        uid = str(uid)
        with self._lock:
            mine = sorted(c for c, u in self.cartels.items() if u == uid)
            winners = []
            if self.phase == "result":
                winners = [{"name": w["name"], "phone": w["phone"], "cartel": w["cartel"],
                            "prize": w["prize"], "mine": w["uid"] == uid} for w in self.winners]
            return {
                "round_id": self.round_id,
                "seq": self._seq,
                "phase": self.phase,
                "server_time": self.clock(),
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

    # ------------------------------------------------------- internal: rounds
    def _new_round(self):
        now = self.clock()
        self.round_id = f"r{int(now * 1000)}"
        self.phase = "selection"
        self.phase_ends_at = now + self.selection_seconds
        self.cartels = {}          # cartel -> uid (picks, then locked tickets)[span_8](start_span)[span_8](end_span)
        self.draw_order = []
        self.drawn = []
        self.next_draw_at = None
        self.winners = []
        self.no_winner = False
        self._pending = None
        self._seq += 1

    def _tick(self):
        todo, snapshot = None, None
        with self._lock:
            now = self.clock()
            if self.phase == "selection":
                if now >= self.phase_ends_at:
                    if len(set(self.cartels.values())) < self.min_players:
                        # not enough players: keep the picks and wait another cycle[span_9](start_span)[span_9](end_span)
                        self.phase_ends_at = now + self.selection_seconds
                        self._seq += 1
                    else:
                        self.phase = "locking"
                        self._seq += 1
                        snapshot, todo = dict(self.cartels), "lock"
            elif self.phase == "drawing":
                if now >= self.next_draw_at:
                    self._draw_one(now)
                if self.phase == "settling":
                    todo = "settle"
            elif self.phase == "settling":
                if now >= self._retry_at:
                    todo = "settle"
            elif self.phase == "result":
                if now >= self.phase_ends_at:
                    self._new_round()
        if todo == "lock":
            self._do_lock(snapshot)
        elif todo == "settle":
            self._do_settle()

    def _do_lock(self, snapshot):
        rid = self.round_id
        try:
            # Saved BEFORE any money moves, so a crash can always be refunded on restart.[span_10](start_span)[span_10](end_span)
            self.wallet.begin_round(rid, snapshot)
        except Exception:
            traceback.print_exc()
            self._abort_lock(rid, snapshot, set(snapshot.values()))
            return

        by_user = defaultdict(list)
        for cartel, uid in snapshot.items():
            by_user[uid].append(cartel)

        paid = {}
        for uid, cartels in by_user.items():
            try:
                new_balance = self.wallet.charge(uid, len(cartels) * TICKET_PRICE, rid, cartels=len(cartels))
            except Exception:
                traceback.print_exc()
                new_balance = None
            if new_balance is not None:        
                paid[uid] = cartels
            else:
                try:                            
                    self.wallet.refund(uid, rid)
                except Exception:
                    traceback.print_exc()

        if len(paid) < self.min_players:
            self._abort_lock(rid, snapshot, set(paid))
            return

        tickets = {c: u for u, cs in paid.items() for c in cs}
        try:
            self.wallet.start_drawing(rid, tickets)
        except Exception:
            traceback.print_exc()
            self._abort_lock(rid, snapshot, set(paid))
            return

        order = list(range(1, BALLS + 1))
        self.rng.shuffle(order)
        with self._lock:
            self.cartels = tickets
            self.draw_order = order
            self.drawn = []
            self.phase = "drawing"
            self.next_draw_at = self.clock() + self.first_draw_delay
            self._seq += 1

    def _abort_lock(self, rid, snapshot, keep_users):
        """Give every charge back, go back to selection and keep the picks of `keep_users`.""[span_11](start_span)"[span_11](end_span)
        all_refunded = True
        for uid in set(snapshot.values()):
            try:
                self.wallet.refund(uid, rid)   # safe to repeat: only refunds a charge that exists[span_12](start_span)[span_12](end_span)
            except Exception:
                all_refunded = False
                traceback.print_exc()
                print(f"!! REFUND FAILED user={uid} round={rid} - it will be retried on the next restart")[span_13](start_span)[span_13](end_span)
        if all_refunded:
            try:
                self.wallet.mark_round(rid, "aborted")
            except Exception:
                traceback.print_exc()
        with self._lock:
            self.cartels = {c: u for c, u in snapshot.items() if u in keep_users}
            self.phase = "selection"
            self.phase_ends_at = self.clock() + self.selection_seconds
            self._seq += 1

    def _draw_one(self, now):
        number = self.draw_order[len(self.drawn)]
        self.drawn.append(number)
        self._seq += 1
        drawn_set = set(self.drawn)
        winning = [c for c in sorted(self.cartels) if check_bingo(generate_matrix(c), drawn_set)]
        if winning:
            self._pending, self.phase = ("win", winning), "settling"
        elif len(self.drawn) >= BALLS:
            self._pending, self.phase = ("none", []), "settling"
        else:
            self.next_draw_at = max(self.next_draw_at + self.draw_interval, now)

    def _do_settle(self):
        with self._lock:
            rid, tickets, pending = self.round_id, dict(self.cartels), self._pending
        pool = 0.0
        try:
            if pending[0] == "win":
                wins = pending[1]
                pool = len(tickets) * PRIZE_PER_CARTEL
                share = round(pool / len(wins), 2)
                payouts = defaultdict(float)
                for c in wins:
                    payouts[tickets[c]] = round(payouts[tickets[c]] + share, 2)
                profiles = {}
                for uid in payouts:
                    try:
                        profiles[uid] = self.wallet.profile(uid) or {}
                    except Exception:
                        profiles[uid] = {}
                self.wallet.settle(rid, dict(payouts))
                winners = [{"uid": tickets[c], "cartel": c, "prize": share,
                            "name": profiles[tickets[c]].get("name") or "Player",
                            "username": profiles[tickets[c]].get("username"),
                            "phone": _mask_phone(profiles[tickets[c]].get("phone"))} for c in wins]
                no_winner = False
            else:
                self.wallet.cancel_round(rid, sorted(set(tickets.values())))
                winners, no_winner = [], True
        except Exception:
            traceback.print_exc()
            with self._lock:
                self._retry_at = self.clock() + 2.0    
            return
        with self._lock:
            self.winners = winners
            self.no_winner = no_winner
            self.phase = "result"
            self.phase_ends_at = self.clock() + self.result_seconds
            self._seq += 1
            event = {
                "round_id": rid,
                "players": len(set(tickets.values())),
                "cartels": len(tickets),
                "pool": float(pool),
                "balls": len(self.drawn),
                "no_winner": no_winner,
                "winners": [dict(w) for w in winners],
            }
        self._emit(event)

    def _emit(self, event):
        """Runs the listener in its own thread: a slow or failing alert can never hold up or break the game.""[span_14](start_span)"[span_14](end_span)
        callback = self.on_round_result
        if not callback:
            return

        def run():
            try:
                callback(event)
            except Exception:
                traceback.print_exc()

        threading.Thread(target=run, name="round-alert", daemon=True).start()
