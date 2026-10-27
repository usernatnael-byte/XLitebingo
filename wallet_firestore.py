import logging
from datetime import datetime
import firebase_admin
from firebase_admin import firestore

logger = logging.getLogger(__name__)

class FirestoreWallet:
    def __init__(self):
        try:
            self.db = firestore.client()
        except Exception as e:
            logger.error(f"FirestoreWallet init error: {e}")
            self.db = None
        self._cache = {}

    def get_balance(self, user_id):
        """የተጠቃሚውን ዋና ሂሳብ እና ቦነስ ከካሽ ወይም ከፋየርቤዝ ያመጣል።"""
        user_id = str(user_id)
        if user_id in self._cache:
            return self._cache[user_id]

        if not self.db:
            return 0.0, 0.0

        try:
            doc_ref = self.db.collection("users").document(user_id)
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict() or {}
                balance = float(data.get("balance", 0.0))
                bonus = float(data.get("bonus", 0.0) or 0.0)
                self._cache[user_id] = (balance, bonus)
                return balance, bonus
        except Exception as e:
            logger.error(f"Error getting balance for {user_id}: {e}")

        return 0.0, 0.0

    def cache_set(self, user_id, balance, bonus=0.0):
        """የሂሳብ መጠን በሎካል ካሽ (Cache) ላይ ያዘምናል።"""
        self._cache[str(user_id)] = (float(balance), float(bonus))

    def cache_drop(self, user_id):
        """ካሽ ላይ ያለውን መረጃ ያጠፋል (ዳግም ከፋየርቤዝ እንዲያነብ ለማድረግ)።"""
        user_id = str(user_id)
        if user_id in self._cache:
            del self._cache[user_id]

    def update_balance(self, user_id, amount, tx_type="adjustment"):
        """የተጠቃሚውን ሂሳብ ይጨምራል ወይም ይቀንሳል (Deposit, Withdraw, Win)።"""
        user_id = str(user_id)
        if not self.db:
            return False

        user_ref = self.db.collection("users").document(user_id)

        @firestore.transactional
        def _txn(transaction):
            doc = user_ref.get(transaction=transaction)
            if not doc.exists:
                return None
            
            data = doc.to_dict() or {}
            current_balance = float(data.get("balance", 0.0))
            bonus = float(data.get("bonus", 0.0) or 0.0)

            if tx_type == "withdraw" and current_balance < amount:
                return None  # በቂ ብር ከሌለ

            if tx_type in ["deposit", "win", "refund"]:
                new_balance = current_balance + amount
            elif tx_type == "withdraw":
                new_balance = current_balance - amount
            else:
                new_balance = current_balance + amount

            transactions = data.get("transactions", [])
            transactions.append({
                "type": tx_type,
                "amount": amount,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })

            transaction.update(user_ref, {
                "balance": new_balance,
                "transactions": transactions
            })
            
            return new_balance, bonus

        try:
            result = _txn(self.db.transaction())
            if result:
                new_bal, bon = result
                self.cache_set(user_id, new_bal, bon)
                return True
        except Exception as e:
            logger.error(f"Error updating balance for {user_id}: {e}")

        return False
