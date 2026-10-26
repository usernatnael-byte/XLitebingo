import time
import random
import threading
import logging

logger = logging.getLogger(__name__)

TICKET_PRICE = 10.0
PRIZE_PER_CARTEL = 8.0
MAX_SELECTION = 10

class GameEngine:
    def __init__(self, wallet, min_players=2):
        self.wallet = wallet
        self.min_players = min_players
        self.selection_seconds = 30
        self.draw_interval = 3.0
        self.result_seconds = 10
        self.phase = "selection" # selection, playing, result
        self.selections = {} # user_id -> set of cartels
        self.drawn_numbers = []
        self.current_round = 1
        self.round_start_time = time.time()
        self._thread = None
        self._lock = threading.Lock()
        self.on_round_result = None

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            logger.info("GameEngine loop started.")

    def get_state(self, user_id=None):
        with self._lock:
            user_sels = list(self.selections.get(str(user_id), [])) if user_id else []
            all_picked = [c for sels in self.selections.values() for c in sels]
            return {
                "phase": self.phase,
                "round": self.current_round,
                "ticket_price": TICKET_PRICE,
                "prize_per_cartel": PRIZE_PER_CARTEL,
                "max_selection": MAX_SELECTION,
                "user_selections": user_sels,
                "all_selections": all_picked,
                "drawn_numbers": self.drawn_numbers,
                "time_left": max(0, int(self.selection_seconds - (time.time() - self.round_start_time))) if self.phase == "selection" else 0
            }

    def pick(self, user_id, cartel):
        """Returns (ok, code). Codes: ok, invalid, phase, taken, full, balance, error."""
        uid = str(user_id)
        try:
            cartel_num = int(cartel)
        except (TypeError, ValueError):
            return False, "invalid"

        if not (1 <= cartel_num <= 500):
            return False, "invalid"

        with self._lock:
            if self.phase != "selection":
                return False, "phase"

            # Check if taken by someone else
            for u, sels in self.selections.items():
                if cartel_num in sels and u != uid:
                    return False, "taken"

            user_sels = self.selections.setdefault(uid, set())
            if len(user_sels) >= MAX_SELECTION:
                return False, "full"

            if cartel_num in user_sels:
                return True, "ok"

            # Check wallet balance before picking
            try:
                balance, bonus = self.wallet.get_wallets(uid)
            except Exception:
                balance, bonus = 0.0, 0.0

            total_cost = (len(user_sels) + 1) * TICKET_PRICE
            if (balance + bonus) < total_cost:
                return False, "balance"

            user_sels.add(cartel_num)
            return True, "ok"

    def unpick(self, user_id, cartel):
        uid = str(user_id)
        try:
            cartel_num = int(cartel)
        except (TypeError, ValueError):
            return False, "invalid"

        with self._lock:
            if self.phase != "selection":
                return False, "phase"
            
            user_sels = self.selections.get(uid, set())
            if cartel_num in user_sels:
                user_sels.remove(cartel_num)
                if not user_sels:
                    self.selections.pop(uid, None)
                return True, "ok"
            return False, "invalid"

    def _run_loop(self):
        while True:
            try:
                with self._lock:
                    self.phase = "selection"
                    self.selections = {}
                    self.drawn_numbers = []
                    self.round_start_time = time.time()

                # Wait for selection phase
                time.sleep(self.selection_seconds)

                with self._lock:
                    self.phase = "playing"
                    active_players = [uid for uid, sels in self.selections.items() if sels]
                    
                    # If not enough players, extend or reset round
                    if len(active_players) < self.min_players:
                        self.round_start_time = time.time()
                        continue

                    # Deduct balances for picks
                    for uid, sels in self.selections.items():
                        cost = len(sels) * TICKET_PRICE
                        try:
                            self.wallet.deduct(uid, cost)
                        except Exception as e:
                            logger.error(f"Failed to deduct wallet for {uid}: {e}")

                # Draw numbers (1 to 75)
                numbers = list(range(1, 76))
                random.shuffle(numbers)

                for num in numbers:
                    with self._lock:
                        if self.phase != "playing":
                            break
                        self.drawn_numbers.append(num)
                    time.sleep(self.draw_interval)

                with self._lock:
                    self.phase = "result"
                    winners = []
                    total_pool = sum(len(sels) * PRIZE_PER_CARTEL for sels in self.selections.values())
                    
                    if active_players:
                        winner_uid = random.choice(active_players)
                        win_prize = total_pool
                        winners.append({"uid": winner_uid, "prize": win_prize})
                        try:
                            self.wallet.add_win(winner_uid, win_prize)
                        except Exception as e:
                            logger.error(f"Failed to credit win: {e}")

                    event = {
                        "round": self.current_round,
                        "pool": total_pool,
                        "winners": winners,
                        "no_winner": len(winners) == 0
                    }

                if self.on_round_result:
                    try:
                        self.on_round_result(event)
                    except Exception as e:
                        logger.error(f"Error in on_round_result callback: {e}")

                time.sleep(self.result_seconds)

                with self._lock:
                    self.current_round += 1

            except Exception as e:
                logger.error(f"Error in GameEngine loop: {e}")
                time.sleep(3)
