import threading
import logging

logger = logging.getLogger(__name__)

class FirestoreWallet:
    def __init__(self, db, firestore_module):
        self.db = db
        self.firestore = firestore_module
        self._cache = {}  # user_id -> (balance, bonus)
        self._lock = threading.Lock()

    def cache_set(self, user_id, balance, bonus=0.0):
        with self._lock:
            self._cache[str(user_id)] = (float(balance), float(bonus or 0.0))

    def cache_drop(self, user_id):
        with self._lock:
            self._cache.pop(str(user_id), None)

    def get_wallets(self, user_id):
        uid = str(user_id)
        with self._lock:
            if uid in self._cache:
                return self._cache[uid]
        
        if not self.db:
            return 0.0, 0.0
        
        try:
            doc = self.db.collection("users").document(uid).get()
            if doc.exists:
                data = doc.to_dict() or {}
                balance = float(data.get("balance", 0.0) or 0.0)
                bonus = float(data.get("bonus", 0.0) or 0.0)
                with self._lock:
                    self._cache[uid] = (balance, bonus)
                return balance, bonus
        except Exception as e:
            logger.error(f"Error getting wallet for {uid}: {e}")
        return 0.0, 0.0

    def deduct(self, user_id, amount):
        uid = str(user_id)
        if not self.db:
            raise Exception("Database not initialized")
        
        user_ref = self.db.collection("users").document(uid)

        @self.firestore.transactional
        def _txn(transaction):
            snap = user_ref.get(transaction=transaction)
            if not snap.exists:
                raise Exception("User not found")
            data = snap.to_dict() or {}
            balance = float(data.get("balance", 0.0) or 0.0)
            bonus = float(data.get("bonus", 0.0) or 0.0)
            
            total = balance + bonus
            if total < amount:
                raise Exception("Insufficient funds")
            
            # Deduct from bonus first, then main balance
            rem = amount
            new_bonus = bonus
            new_balance = balance
            
            if new_bonus >= rem:
                new_bonus -= rem
                rem = 0.0
            else:
                rem -= new_bonus
                new_bonus = 0.0
                new_balance -= rem

            transaction.update(user_ref, {
                "balance": new_balance,
                "bonus": new_bonus
            })
            return new_balance, new_bonus

        res = _txn(self.db.transaction())
        if res:
            self.cache_set(uid, res[0], res[1])
        return res

    def add_win(self, user_id, amount):
        uid = str(user_id)
        if not self.db:
            raise Exception("Database not initialized")
        
        user_ref = self.db.collection("users").document(uid)

        @self.firestore.transactional
        def _txn(transaction):
            snap = user_ref.get(transaction=transaction)
            if not snap.exists:
                raise Exception("User not found")
            data = snap.to_dict() or {}
            balance = float(data.get("balance", 0.0) or 0.0)
            bonus = float(data.get("bonus", 0.0) or 0.0)
            
            new_balance = balance + amount
            transaction.update(user_ref, {
                "balance": new_balance
            })
            return new_balance, bonus

        res = _txn(self.db.transaction())
        if res:
            self.cache_set(uid, res[0], res[1])
        return res
