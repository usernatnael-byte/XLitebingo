import telebot
from telebot import types
from datetime import datetime
from threading import Thread
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, request, jsonify, send_file, g
from flask_cors import CORS
import os
import hmac
from urllib.parse import urlparse
from tg_auth import require_telegram_auth
from game_engine import GameEngine, TICKET_PRICE, PRIZE_PER_CARTEL, MAX_SELECTION
from wallet_firestore import FirestoreWallet
import time
from collections import defaultdict, deque

# Initialize Firebase Connection
cred = credentials.Certificate(os.environ.get("FIREBASE_KEY_PATH", "firebase_key.json"))
firebase_admin.initialize_app(cred)

# Create the database object
db = firestore.client()

def process_transaction(user_id, tx_type, amount, bonus_add=0.0):
    """Deposit / withdraw / refund as ONE atomic Firestore transaction (safe next to the game's own money moves)."""
    user_ref = db.collection("users").document(str(user_id))

    @firestore.transactional
    def _apply(transaction):
        user_doc = user_ref.get(transaction=transaction)
        if not user_doc.exists:
            return None
        user_data = user_doc.to_dict() or {}
        current_balance = user_data.get('balance', 0.0)
        bonus_part = float(user_data.get('bonus', 0) or 0)
        if tx_type == 'withdraw' and current_balance - amount < bonus_part - 1e-9:
            return None                              # would dip into the play wallet (or below zero)

        if tx_type == 'deposit' or tx_type == 'refund':
            new_balance = current_balance + amount
        elif tx_type == 'withdraw':
            new_balance = current_balance - amount
        else:
            new_balance = current_balance

        transactions = user_data.get('transactions', [])
        transactions.append({
            "type": tx_type,
            "amount": amount,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
        extra = {}
        if tx_type == 'deposit' and bonus_add > 0:                 # deposit bonus: goes to the play wallet, in the same transaction
            new_balance += bonus_add
            extra["bonus"] = round(bonus_part + bonus_add, 2)
            transactions.append({"type": "deposit_bonus", "amount": bonus_add, "timestamp": datetime.utcnow().isoformat() + "Z"})
            user_data['bonus'] = extra["bonus"]
        transaction.update(user_ref, {"balance": new_balance, "transactions": transactions, **extra})

        user_data['balance'] = new_balance
        user_data['transactions'] = transactions
        return user_data

    result = _apply(db.transaction())
    if result:
        try:
            wallet.cache_set(user_id, float(result.get('balance', 0)), float(result.get('bonus', 0) or 0))
        except Exception:
            pass
    return result

def update_profile_stats(user_id, round_id=None, win_amount=0.0):
    user_ref = db.collection('users').document(str(user_id))
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        return {"error": "User not found"}
        
    user_data = user_doc.to_dict()
    updates = {}
    
    # 1. Update Winnings
    if float(win_amount) > 0:
        current_winnings = float(user_data.get('total_winnings', 0.0))
        updates['total_winnings'] = current_winnings + float(win_amount)
        
    # 2. Update Games Played (Strictly 1 per round)
    if round_id:
        last_round = str(user_data.get('last_played_round', ''))
        current_round = str(round_id)
        
        # Only add +1 if this round ID is different from the last round they played
        if current_round != last_round:
            current_games = int(user_data.get('total_games_played', 0))
            updates['total_games_played'] = current_games + 1
            updates['last_played_round'] = current_round
            
    # 3. Merge updates into Firebase securely
    if updates:
        user_ref.set(updates, merge=True)
        
    return updates
# --------------------------------------

print("✅ Successfully connected to Firebase Database!")


TOKEN = os.environ["8747562686:AAGQCIOwD3ahfjVY21PY4gvftQCtxaq0UNA"]  
WEBAPP_URL = os.environ["https://xlitebingo.onrender.com"]  
_u = urlparse(WEBAPP_URL)
WEBAPP_ORIGIN = f"{_u.scheme}://{_u.netloc}"
RESET_TOKEN = os.environ.get("MySuperSecretBingoTokenN2026", "")  

bot = telebot.TeleBot(TOKEN)

ADMIN_ID = 7396414604  # <--- ከ "7396414604" ይልቅ የእርስዎን ትክክለኛ የቴሌግራም ID ያስገቡ

# ==========================================
# 🗄️ FIREBASE DATABASE FUNCTIONS
# ==========================================
def get_balance(user_id):
    """Reads the user's balance from Firestore."""
    doc = db.collection("users").document(str(user_id)).get()
    return doc.to_dict().get("balance", 0.0) if doc.exists else 0.0

def update_balance(user_id, amount_to_add, first_name="User", username=""):
    """Adds or subtracts from the user's balance in Firestore."""
    doc_ref = db.collection("users").document(str(user_id))
    doc = doc_ref.get()
    
    if doc.exists:
        current = doc.to_dict().get("balance", 0.0)
        new_balance = current + amount_to_add
        doc_ref.update({"balance": new_balance})
        return new_balance
    else:
        # If the user doesn't exist yet, create their profile in the database
        doc_ref.set({
            "balance": amount_to_add,
            "first_name": first_name,
            "username": username
        })
        return amount_to_add

def get_main_menu():
    # Creates a custom reply keyboard that fits nicely on mobile screens
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)

    # Action Buttons (No Play button here!)
    btn_account = types.KeyboardButton(text="💼 የኔ ሂሳብ (Account)")
    btn_refer = types.KeyboardButton(text="🎁 ጋብዝ እና አግኝ (Refer)")
    btn_deposit = types.KeyboardButton(text="📥 ገቢ (Deposit)")
    btn_withdraw = types.KeyboardButton(text="📤 ወጪ (Withdraw)")
    btn_help = types.KeyboardButton(text="🎧 እርዳታ ማዕከል (Help & Support)")

    # Building the layout row by row
    markup.add(btn_account, btn_refer)          # Row 2: Account | Refer
    markup.add(btn_deposit, btn_withdraw)       # Row 3: Deposit | Withdraw
    markup.add(btn_help)                        # Row 4: Full width Help button

    return markup

REFERRAL_BONUS = 10.0  
NEW_USER_BONUS = 5.0  

WITHDRAW_REQUIRES_DEPOSIT = os.environ.get("WITHDRAW_REQUIRES_DEPOSIT", "1") == "1"

def withdraw_block_message(user_data):
    """Message if this player may not withdraw yet, else None.
    Rule: after every bonus, the player must make at least one deposit before withdrawing."""
    if not WITHDRAW_REQUIRES_DEPOSIT:
        return None
    txs = (user_data or {}).get("transactions") or []         # oldest first
    last_bonus = max((i for i, t in enumerate(txs) if t.get("type") == "bonus"), default=-1)
    if last_bonus >= 0 and not any(t.get("type") == "deposit" for t in txs[last_bonus + 1:]):
        return "⚠️ ቦነስ ካገኙ በኋላ ገንዘብ ከማውጣትዎ በፊት ቢያንስ አንድ ጊዜ ገቢ (Deposit) ማድረግ አለብዎት።"
    return None

def get_bonus_amounts():
    """(inviter_bonus, newcomer_bonus). Set live with /setbonus; falls back to the defaults above."""
    try:
        d = db.collection("settings").document("bonus").get().to_dict() or {}
        return float(d.get("referrer", REFERRAL_BONUS)), float(d.get("newcomer", NEW_USER_BONUS))
    except Exception:
        return REFERRAL_BONUS, NEW_USER_BONUS

def _apply_referral(new_user_id, inviter_bonus, newcomer_bonus):
    """Pays BOTH sides in one atomic transaction, exactly once. Returns the inviter's id, or None.
    A bonus set to 0 pays no money, but the invite is still counted."""
    new_ref = db.collection("users").document(str(new_user_id))

    @firestore.transactional
    def run(txn):
        new_snap = new_ref.get(transaction=txn)
        new_data = (new_snap.to_dict() or {}) if new_snap.exists else {}
        referrer_id = new_data.get("referred_by")
        if not referrer_id or new_data.get("referral_bonus_paid") or str(referrer_id) == str(new_user_id):
            return None
        referrer_ref = db.collection("users").document(str(referrer_id))
        referrer_snap = referrer_ref.get(transaction=txn)
        if not referrer_snap.exists:
            return None
        stamp = datetime.utcnow().isoformat() + "Z"

        new_update = {"referral_bonus_paid": True}
        if newcomer_bonus > 0:
            new_update["balance"] = firestore.Increment(newcomer_bonus)
            new_update["bonus"] = firestore.Increment(newcomer_bonus)
            new_update["transactions"] = firestore.ArrayUnion([
                {"type": "bonus", "amount": newcomer_bonus, "timestamp": stamp, "note": "referral_welcome"}
            ])
        inviter_update = {"referrals_count": firestore.Increment(1)}
        if inviter_bonus > 0:
            inviter_update["balance"] = firestore.Increment(inviter_bonus)
            inviter_update["bonus"] = firestore.Increment(inviter_bonus)
            inviter_update["referral_earnings"] = firestore.Increment(inviter_bonus)
            inviter_update["transactions"] = firestore.ArrayUnion([
                {"type": "bonus", "amount": inviter_bonus, "timestamp": stamp, "note": "referral_invite"}
            ])
        txn.update(new_ref, new_update)
        txn.update(referrer_ref, inviter_update)
        return str(referrer_id)

    return run(db.transaction())

def maybe_pay_referral(new_user_id, phone_number):
    """Called when a player shares their own phone number. Pays the referral bonus once."""
    try:
        new_ref = db.collection("users").document(str(new_user_id))
        data = new_ref.get().to_dict() or {}
        if not data.get("referred_by") or data.get("referral_bonus_paid") or data.get("referral_blocked"):
            return
        # The same phone number on another account means this is not a new person.
        others = [d.id for d in db.collection("users").where("phone_number", "==", phone_number).limit(3).stream()
                  if d.id != str(new_user_id)]
        if others:
            new_ref.set({"referral_blocked": "duplicate_phone"}, merge=True)
            bot.send_message(ADMIN_ID, f"⚠️ Referral bonus skipped for {new_user_id}: phone {phone_number} "
                                       f"is already used by account {others[0]}.")
            return
        inviter_bonus, newcomer_bonus = get_bonus_amounts()
        referrer_id = _apply_referral(new_user_id, inviter_bonus, newcomer_bonus)
        if not referrer_id:
            return
        try:
            wallet.cache_drop(new_user_id)
            wallet.cache_drop(referrer_id)
        except Exception:
            pass
        name = data.get("first_name") or "ጓደኛዎ"
        notes = []
        if newcomer_bonus > 0:
            notes.append((new_user_id, f"🎁 እንኳን ደስ አለዎት! በጓደኛዎ ግብዣ ስለተቀላቀሉ {newcomer_bonus:g} ETB ቦነስ ወደ ሂሳብዎ ተጨምሯል።"))
        invited_text = f"🎉 {name} በእርስዎ ሊንክ ተቀላቅሏል!"
        if inviter_bonus > 0:
            invited_text += f" {inviter_bonus:g} ETB ቦነስ ወደ ሂሳብዎ ተጨምሯል።"
        notes.append((referrer_id, invited_text))
        for chat_id, text in notes:
            try:
                bot.send_message(int(chat_id), text)
            except Exception:
                pass          # e.g. the person blocked the bot; the money is already paid
    except Exception as e:
        print(f"referral error for {new_user_id}: {e}")
# <<REFERRAL-END>>

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.chat.id
    first_name = message.from_user.first_name
    username = message.from_user.username or ""

    user_ref = db.collection("users").document(str(user_id))
    user_doc = user_ref.get()

    args = message.text.split()

    # Handle WebApp redirect buttons (deposit / withdraw)
    if len(args) > 1:
        if args[1] == "deposit":
            deposit_step_1_method(message)
            return
        elif args[1] == "withdraw":
            withdraw_step_1_method(message)
            return

    # Fetch existing user data
    user_data = user_doc.to_dict() if user_doc.exists else {}

    # 1. Process referral link if brand new user
    if not user_doc.exists:
        referred_by = None
        initial_balance = 0.0

        if len(args) > 1 and args[1].startswith("ref_"):
            try:
                referrer_id = int(args[1].replace("ref_", ""))
                if referrer_id != user_id:
                    referred_by = str(referrer_id)
            except ValueError:
                pass

        user_ref.set({
            "telegram_id": str(user_id),
            "first_name": first_name,
            "username": username,
            "balance": initial_balance,
            "referred_by": referred_by,
            "created_at": firestore.SERVER_TIMESTAMP
        })

    # 2. If phone number is missing, ask for it
    if "phone_number" not in user_data:
        markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton("📱 Share Phone Number", request_contact=True))
        bot.send_message(
            message.chat.id,
            f"Hello {first_name}! Welcome to Bingo Bot.\n\nPlease tap the button below to share your phone number and complete registration:",
            reply_markup=markup
        )
        return

# 3. If phone number exists, restore bottom menu AND send inline Play button
    main_menu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_account = types.KeyboardButton(text="💼 የኔ ሂሳብ (Account)")
    btn_refer = types.KeyboardButton(text="🎁 ጋብዝ እና አግኝ (Refer)")
    btn_deposit = types.KeyboardButton(text="📥 ገቢ (Deposit)")
    btn_withdraw = types.KeyboardButton(text="📤 ወጪ (Withdraw)")
    btn_help = types.KeyboardButton(text="🎧 እርዳታ ማዕከል (Help & Support)")
    main_menu.add(btn_account, btn_refer, btn_deposit, btn_withdraw, btn_help)

    bot.send_message(
        message.chat.id,
        f"Welcome back, {first_name}!",
        reply_markup=main_menu
    )

    inline_markup = types.InlineKeyboardMarkup()
    inline_markup.add(types.InlineKeyboardButton("🎮 Play Bingo", web_app=types.WebAppInfo(url=WEBAPP_URL)))
    
    bot.send_message(
        message.chat.id,
        "Tap below to play:",
        reply_markup=inline_markup
    )

# --- CONTACT HANDLER (Saves Phone Number to Firestore) ---
@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    if message.contact is not None:
        # Only accept the player's OWN number (blocks forwarded contacts / other people's numbers)
        if message.contact.user_id != message.from_user.id:
            bot.send_message(message.chat.id, "⚠️ እባክዎን በታች ባለው ቁልፍ የራስዎን ስልክ ቁጥር ብቻ ያጋሩ።")
            return
        user_id = str(message.chat.id)
        phone_number = message.contact.phone_number

        if not phone_number.startswith("+"):
            phone_number = "+" + phone_number

        user_ref = db.collection("users").document(user_id)
        user_ref.set({
            "phone_number": phone_number
        }, merge=True)

       # 1. Restore the main bottom menu
        main_menu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        btn_account = types.KeyboardButton(text="💼 የኔ ሂሳብ (Account)")
        btn_refer = types.KeyboardButton(text="🎁 ጋብዝ እና አግኝ (Refer)")
        btn_deposit = types.KeyboardButton(text="📥 ገቢ (Deposit)")
        btn_withdraw = types.KeyboardButton(text="📤 ወጪ (Withdraw)")
        btn_help = types.KeyboardButton(text="🎧 እርዳታ ማዕከል (Help & Support)")
        main_menu.add(btn_account, btn_refer, btn_deposit, btn_withdraw, btn_help)
        bot.send_message(
            message.chat.id,
            "✅ Phone number registered successfully!",
            reply_markup=main_menu
        )

        # 2. Send the inline Play button
        inline_markup = types.InlineKeyboardMarkup()
        inline_markup.add(types.InlineKeyboardButton("🎮 Play Bingo", web_app=types.WebAppInfo(url=WEBAPP_URL)))

        bot.send_message(
            message.chat.id,
            "Tap below to open the WebApp:",
            reply_markup=inline_markup
        )

        
        maybe_pay_referral(user_id, phone_number)
    
    # ==========================================
# 💼 ACCOUNT / PROFILE BUTTON LOGIC
# ==========================================
@bot.message_handler(func=lambda message: message.text == "💼 የኔ ሂሳብ (Account)")
def show_profile(message):
    user_name = message.from_user.first_name
    user_id = str(message.chat.id)

    # Fetch live data directly from the database
    user_doc = db.collection("users").document(user_id).get()
    
    play_balance = 0.0
    phone = "አልተመዘገበም"
    
    if user_doc.exists:
        user_data = user_doc.to_dict()
        play_balance = float(user_data.get("bonus", 0.0) or 0.0)
        main_balance = float(user_data.get("balance", 0.0)) - play_balance
        phone = user_data.get("phone_number", "አልተመዘገበም")

    profile_msg = (
        "👤 *የእርስዎ ፕሮፋይል (Your Profile)*\n"
        "───────────────\n"
        f"🔹 *ስም (Name):* {user_name}\n"
        f"🔹 *ስልክ (Phone):* {phone}\n\n"
        f"💰 *የጨዋታ ሂሳብ (Play Balance):* {play_balance:.2f} ETB\n"
        f"🏦 *ዋና ሂሳብ (Main Balance):* {main_balance:.2f} ETB\n"
        f"🏆 *የአሸናፊነት ሂሳብ (Win Balance):* 0.00 ETB\n"
        "───────────────\n"
        "💡 *ወደ ጨዋታ ሂሳብዎ ብር ለመጨመር '📥 ገቢ (Deposit)' የሚለውን ይጫኑ::*"
    )
    
    bot.send_message(message.chat.id, profile_msg, parse_mode="Markdown")
 # ==========================================
# 📥 DEPOSIT BUTTON LOGIC (Multi-step)
# ==========================================

# Step 1: User clicks Deposit from main menu
@bot.message_handler(func=lambda message: message.text == "📥 ገቢ (Deposit)")
def deposit_step_1_method(message):
    print(">>> Deposit button was pressed by user!")
    bot.clear_step_handler_by_chat_id(message.chat.id) # Fixes the stuck issue
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_telebirr = types.InlineKeyboardButton("Telebirr 📱", callback_data="dep_telebirr")
    btn_cbe = types.InlineKeyboardButton("CBEBirr 🏦", callback_data="dep_cbebirr")
    markup.add(btn_telebirr, btn_cbe)
    
    bot.send_message(
        message.chat.id, 
        "💰 ሂሳብ ለመሙላት የሚጠቀሙበትን የክፍያ አማራጭ ይምረጡ፡-", 
        reply_markup=markup
    )

# Step 2: Handle the Inline Button Click (Telebirr or CBEBirr)
@bot.callback_query_handler(func=lambda call: call.data in ['dep_telebirr', 'dep_cbebirr'])
def deposit_step_2_amount(call):
    method = "Telebirr" if call.data == "dep_telebirr" else "CBEBirr"
    bot.answer_callback_query(call.id)
    
    msg = bot.send_message(
        call.message.chat.id,
        f"እባክዎ በ {method} ማስገባት የሚፈልጉትን የብር መጠን ያስገቡ\n*(አነስተኛ መጠን: 50 ETB)*",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_deposit_amount, method)

# Step 3: Validate Amount
def process_deposit_amount(message, method):
    if message.text in ["💼 የኔ ሂሳብ (Account)", "📥 ገቢ (Deposit)", "📤 ወጪ (Withdraw)", "🎁 ጋብዝ እና አግኝ (Refer)", "🎧 እርዳታ ማዕከል (Help & Support)"]:
        bot.send_message(message.chat.id, "ሂደቱ ተቋርጧል። (Process cancelled.)")
        return

    try:
        amount = float(message.text)
        if amount < 50:
            msg = bot.send_message(message.chat.id, "⚠️ ይቅርታ፣ ማስገባት የሚችሉት አነስተኛ መጠን **50 ETB** ነው።\nእባክዎ ትክክለኛ መጠን ያስገቡ፦", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_deposit_amount, method)
        else:
            instructions = (
                f"{deposit_offer_line(amount)}"
                f"መሙላት የፈለጉት መጠን: **{amount:g} ETB**\n\n"
                f"እባክዎ ከታች ወዳለው የ{method} አካውንት ብሩን ያስገቡ።\n"
                f"👤 ስም: **Esrale**\n"
                f"📱 አካውንት: **0949196145**\n\n"
                f"የላኩበትን ማረጋገጫ አንዱን ይላኩልን፦\n"
                f"1️⃣ ሚሴጅ (SMS)\n"
                f"2️⃣ የደረሰኝ ፎቶ (screenshot)\n"
            )
            msg = bot.send_message(message.chat.id, instructions, parse_mode="Markdown")
            bot.register_next_step_handler(msg, receive_payment_proof, method, amount)
            
    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ የተሳሳተ ቁጥር! እባክዎ የብር መጠኑን በቁጥር ብቻ ያስገቡ (ለምሳሌ፦ 100)፡")
        bot.register_next_step_handler(msg, process_deposit_amount, method)

# <<RECEIPT-BEGIN>>
# Text proofs must be a real-looking Telebirr / CBE message sent TO the admin. Screenshots are accepted as before.
import re
RECEIVER_TOKENS = [t for t in os.environ.get("RECEIVER_NAME", "zeid fenta").lower().split() if t]
MENU_TEXTS = ["💼 የኔ ሂሳብ (Account)", "📥 ገቢ (Deposit)", "📤 ወጪ (Withdraw)", "🎁 ጋብዝ እና አግኝ (Refer)", "🎧 እርዳታ ማዕከል (Help & Support)"]

INVALID_MSG = ("❌ Invalid. Please input the proper text message or screenshot (recommended).\n"
               "❌ ልክ አይደለም። እባክዎ ትክክለኛውን የክፍያ መልእክት (text) ወይም ስክሪንሾት (የሚመከር) ያስገቡ።")
WRONG_RECEIVER_MSG = "❌ ገንዘቡ ወደ ትክክለኛው አካውንት አልተላከም። (The money must be sent to the account shown above.)"
USED_MSG = "❌ ይህ ደረሰኝ ቀድሞ ጥቅም ላይ ውሏል። (This receipt was already used.)"

_TB = re.compile(r"you have transferred etb\s*([\d,]+(?:\.\d+)?)\s+to\s+(.+?)\s*\(([\d*]+)\)\s+on\s+\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\.?\s*your transaction number is\s+([a-z0-9]{8,14})", re.I)
_TB_LINK = re.compile(r"ethiotelecom\.et/receipt/([a-z0-9]+)", re.I)
_CBE = re.compile(r"you have successfully transferred etb\s*([\d,]+(?:\.\d+)?)\s+from account\s+(\S+)\s+to account\s+(\S+)\s*\((.+?)\)", re.I)
_CBE_BAL = re.compile(r"current balance is etb\s*([\d,]+(?:\.\d+)?)", re.I)
_CBE_LINK = re.compile(r"cbe\.com\.et/([A-Za-z0-9_-]+)")

def _clean_key(k):
    return re.sub(r"[^A-Za-z0-9_-]", "_", k)[:120]

def validate_receipt(text, method, declared_amount):
    """(True, {'amount','key','ref'}) or (False, 'format' | 'receiver' | 'amount')."""
    t = " ".join((text or "").split())
    if method == "Telebirr":
        m = _TB.search(t)
        if not m:
            return False, "format"
        amount, receiver, code = float(m.group(1).replace(",", "")), m.group(2), m.group(4).upper()
        link = _TB_LINK.search(t)
        if link and link.group(1).upper() != code:         # the link must carry the same transaction number
            return False, "format"
        key, ref = "tb_" + code, code
    else:
        m = _CBE.search(t)
        if not m:
            return False, "format"
        amount, receiver = float(m.group(1).replace(",", "")), m.group(4)
        link, bal = _CBE_LINK.search(t), _CBE_BAL.search(t)
        if link:
            key, ref = "cbe_" + link.group(1), link.group(1)
        elif bal:                                         # no link pasted: sender + amount + balance is unique per transfer
            key, ref = f"cbe_{m.group(2)}_{amount:g}_{bal.group(1)}", f"{m.group(2)}/{bal.group(1)}"
        else:
            return False, "format"
    if not all(tok in receiver.lower() for tok in RECEIVER_TOKENS):
        return False, "receiver"
    if abs(amount - float(declared_amount)) > 0.01:
        return False, "amount"
    return True, {"amount": amount, "key": _clean_key(key), "ref": ref}

def _claim_receipt(key, user_id, amount, method):
    """True = new receipt, False = already used. Other database errors are raised."""
    try:
        db.collection("receipts").document(key).create({
            "user_id": str(user_id), "amount": amount, "method": method, "status": "pending",
            "at": datetime.utcnow().isoformat() + "Z"})
        return True
    except Exception as e:
        if e.__class__.__name__ == "AlreadyExists":
            return False
        raise

def _settle_receipts(user_id, approved):
    """Approved deposit: keep the receipt blocked. Rejected: free it so the player can send a corrected one."""
    try:
        for d in db.collection("receipts").where("user_id", "==", str(user_id)).where("status", "==", "pending").limit(5).stream():
            d.reference.update({"status": "approved"}) if approved else d.reference.delete()
    except Exception as e:
        print(f"receipt settle error: {e}")
# <<RECEIPT-END>>

# Step 4: Receive Proof and Send to Admin
def receive_payment_proof(message, method, amount):
    user_id = message.chat.id
    if message.text and message.text in MENU_TEXTS:                  # tapped a menu button: cancel
        bot.send_message(user_id, "ሂደቱ ተሰርዟል። (Process cancelled.)")
        return
    check_note = "🖼 Screenshot: please verify it yourself"
    if not message.photo:
        ok, info = validate_receipt(message.text, method, amount)
        if not ok:
            reply = {"receiver": WRONG_RECEIVER_MSG, "amount": f"❌ በመልእክቱ ላይ ያለው መጠን ከ {amount:g} ETB ጋር አይመሳሰልም። (Amount does not match.)"}.get(info, INVALID_MSG)
            msg = bot.send_message(user_id, reply)
            bot.register_next_step_handler(msg, receive_payment_proof, method, amount)
            return
        try:
            fresh = _claim_receipt(info["key"], user_id, amount, method)
        except Exception as e:
            print(f"receipt claim error: {e}")
            fresh = None
        if fresh is False:
            msg = bot.send_message(user_id, USED_MSG)
            bot.register_next_step_handler(msg, receive_payment_proof, method, amount)
            return
        check_note = f"✅ Text checked (receiver + amount OK) · Ref {info['ref']}" + ("" if fresh else " · ⚠️ duplicate check unavailable")
    proof_text = message.text or message.caption or "ፎቶ ብቻ (Photo only)"
    username = message.from_user.username or "No Username"

    user_confirmation = (
        "✅ የገቢ ጥያቄዎ ተልኳል!\n\n"
        f"🔹 ባንክ: {method}\n"
        f"🔹 መጠን: {amount} ETB\n"
        f"🔹 ማስታወሻ: {proof_text}\n\n"
        "ክፍያው ከተረጋገጠ በኋላ ሂሳብ ወዲያውኑ ይስተካከላል። እናመሰግናለን!"
    )
    bot.send_message(user_id, user_confirmation)

    admin_msg = (
        "🚨 አዲስ የገቢ ጥያቄ (NEW DEPOSIT REQUEST)\n\n"
        f"👤 ተጠቃሚ: {message.from_user.first_name} (@{username})\n"
        f"🆔 User ID: {user_id}\n"
        f"🏦 ባንክ: {method}\n"
        f"💵 መጠን: {amount} ETB\n"
        f"📝 Tx Ref/SMS: {proof_text}\n"
        f"{check_note}"
    )
    
    markup = types.InlineKeyboardMarkup()
    btn_approve = types.InlineKeyboardButton("✅ አፅድቅ (Approve)", callback_data=f"app_{user_id}_{amount}")
    btn_reject = types.InlineKeyboardButton("❌ ውድቅ አድርግ (Reject)", callback_data=f"rej_{user_id}")
    markup.add(btn_approve, btn_reject)

    if message.photo:
        bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=admin_msg, reply_markup=markup)
    else:
        bot.send_message(ADMIN_ID, admin_msg, reply_markup=markup)

# Step 5: Admin Approval Logic
@bot.callback_query_handler(func=lambda call: call.data.startswith('app_') or call.data.startswith('rej_'))
def handle_admin_decision(call):
    if call.message.chat.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "You are not authorized.")
        return

    data = call.data.split('_')
    action = data[0]
    target_user_id = int(data[1])

    if action == "app":
        amount = float(data[2])
        
        # 🔴 CHANGED: Use process_transaction instead of update_balance so the history ledger updates
        bonus_add = deposit_bonus_for(amount)                  # 0 unless a deposit-bonus campaign is on
        updated_data = process_transaction(target_user_id, 'deposit', amount, bonus_add)
        _settle_receipts(target_user_id, True)
        new_total = updated_data.get('balance', 0.0) - float(updated_data.get('bonus', 0) or 0)
        
        bot.send_message(
            target_user_id, 
            f"✅ የ {amount} ETB ገቢዎ ጸድቋል!\nአሁን አጠቃላይ ሂሳብዎ: **{new_total} ETB** ሆኗል:: መልካም እድል!", 
            parse_mode="Markdown"
        )
        new_text = (call.message.caption or call.message.text) + "\n\n✅ **(APPROVED & CREDITED IN FIREBASE)**"
        if bonus_add > 0:
            bot.send_message(target_user_id, f"🎁 የተቀማጭ ቦነስ: +{bonus_add:g} ETB ወደ የጨዋታ ሂሳብዎ ተጨምሯል! ለመጫወት ተዘጋጅተዋል።")
            new_text += f"\n🎁 Deposit bonus +{bonus_add:g} ETB (play wallet)"
        
    elif action == "rej":
        _settle_receipts(target_user_id, False)
        bot.send_message(target_user_id, "❌ ይቅርታ፣ የገቢ ጥያቄዎ ውድቅ ተደርጓል። እባክዎ መረጃዎን አስተካክለው እንደገና ይሞክሩ።")
        new_text = (call.message.caption or call.message.text) + "\n\n❌ **(REJECTED)**"

    if call.message.photo:
        bot.edit_message_caption(caption=new_text, chat_id=ADMIN_ID, message_id=call.message.message_id, parse_mode="Markdown")
    else:
        bot.edit_message_text(text=new_text, chat_id=ADMIN_ID, message_id=call.message.message_id, parse_mode="Markdown")
# ==========================================
# 📤 WITHDRAW BUTTON LOGIC (Multi-step)
# ==========================================

# Step 1: User clicks Withdraw
@bot.message_handler(func=lambda message: message.text == "📤 ወጪ (Withdraw)")
def withdraw_step_1_method(message):
    bot.clear_step_handler_by_chat_id(message.chat.id)
    user_id = str(message.chat.id)

    # 🟢 Fetch user balance directly from Firebase Firestore
    user_ref = db.collection("users").document(user_id)
    user_doc = user_ref.get()
    
    balance = 0.0
    bonus_part = 0.0
    user_data = {}
    if user_doc.exists:
        user_data = user_doc.to_dict()
        bonus_part = float(user_data.get("bonus", 0.0) or 0.0)
        balance = float(user_data.get("balance", 0.0)) - bonus_part      # only the MAIN wallet can be withdrawn

    # Require at least 100 ETB to withdraw
    if balance < 100:
        bot.send_message(
            message.chat.id,
            f"⚠️ ይቅርታ፤ አነስተኛው የወጪ መጠን **100 ETB** ነው።\nአሁን ያለውት ሂሳብ: **{balance:.2f} ETB**" + (f"\n🎁 የጨዋታ (ቦነስ) ሂሳብዎ {bonus_part:.2f} ETB ለመጫወት ብቻ ነው፣ ሊወጣ አይችልም።" if bonus_part else ""),
            parse_mode="Markdown"
        )
        return

    blocked = withdraw_block_message(user_data)
    if blocked:
        bot.send_message(message.chat.id, blocked)
        return

    # If they have enough, ask for bank choice
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_telebirr = types.InlineKeyboardButton("Telebirr 📱", callback_data="wit_telebirr")
    btn_cbe = types.InlineKeyboardButton("CBEBirr 🏦", callback_data="wit_cbebirr")
    markup.add(btn_telebirr, btn_cbe)

    bot.send_message(
        message.chat.id,
        f"አሁን ያለውት ሂሳብ: **{balance:.2f} ETB**\n\nበወጪ ማድረግ የሚፈልጉትን ባንክ ይምረጡ:-",
        reply_markup=markup,
        parse_mode="Markdown"
    )
# Step 2: Handle Bank Selection
@bot.callback_query_handler(func=lambda call: call.data in ['wit_telebirr', 'wit_cbebirr'])
def withdraw_step_2_amount(call):
    method = "Telebirr" if call.data == "wit_telebirr" else "CBEBirr"
    bot.answer_callback_query(call.id)
    
    msg = bot.send_message(
        call.message.chat.id,
        f"እባክዎ በ {method} ማውጣት የሚፈልጉትን የብር መጠን ያስገቡ\n*(አነስተኛ መጠን: 100 ETB)*",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_withdraw_amount, method)

# Step 3: Validate Withdraw Amount
def process_withdraw_amount(message, method):
    if message.text in ["💼 የኔ ሂሳብ (Account)", "📥 ገቢ (Deposit)", "📤 ወጪ (Withdraw)", "🎁 ጋብዝ እና አትርፍ (Refer)", "🎧 እርዳታ ማእከል (Help & Support)"]:
        bot.send_message(message.chat.id, "ሂደቱ ተቋርጧል። (Process cancelled.)")
        return

    user_id = str(message.chat.id)
    
    # 🟢 Fetch real-time balance from Firebase Firestore
    user_ref = db.collection("users").document(user_id)
    user_doc = user_ref.get()
    balance = 0.0
    if user_doc.exists:
        balance = float(user_doc.to_dict().get("balance", 0.0)) - float(user_doc.to_dict().get("bonus", 0.0) or 0.0)   # main wallet only

    try:
        amount = float(message.text)
        if amount < 100:
            msg = bot.send_message(
                message.chat.id, 
                "⚠️ ይቅርታ፤ ማውጣት የሚችሉት አነስተኛው መጠን **100 ETB** ነው።\nእባክዎ ትክክለኛ መጠን ያስገቡ:-", 
                parse_mode="Markdown"
            )
            bot.register_next_step_handler(msg, process_withdraw_amount, method)
        elif amount > balance:
            bot.send_message(
                message.chat.id, 
                f"❌ በቂ ሂሳብ የለዎትም! (Insufficient funds)\nያለዎት ሂሳብ: **{balance:.2f} ETB**", 
                parse_mode="Markdown"
            )
        else:
            msg = bot.send_message(
                message.chat.id, 
                f"መጠን: **{amount:g}** ETB\n\nእባክዎን የ {method} አካውንት ቁጥርዎን / ስልክዎን በትክክል ያስገቡ:-", 
                parse_mode="Markdown"
            )
            bot.register_next_step_handler(msg, receive_withdraw_account, method, amount)

    except ValueError:
        msg = bot.send_message(message.chat.id, "❌ የተሳሳተ ቁጥር! እባክዎን የብር መጠኑን በቁጥር ብቻ ያስገቡ:")
        bot.register_next_step_handler(msg, process_withdraw_amount, method)
import re

# Step 4: Receive & Validate Account/Phone Number
def receive_withdraw_account(message, method, amount):
    # Check if user clicked a menu button to cancel
    if message.text in ["💼 የኔ ሂሳብ (Account)", "📥 ገቢ (Deposit)", "📤 ወጪ (Withdraw)", "🎁 ጋብዝ እና አትርፍ (Refer)", "🎧 እርዳታ ማእከል (Help & Support)"]:
        bot.send_message(message.chat.id, "ሂደቱ ተቋርጧል። (Process cancelled.)")
        return

    account_info = message.text.strip()

    # Validate that the input consists ONLY of digits and is between 10 to 16 digits long (e.g. 0935084226 or CBE accounts)
    if not re.match(r"^\d{10,16}$", account_info):
        msg = bot.send_message(
            message.chat.id,
            "❌ **የተሳሳተ የቁጥር ቅርጸት!**\n\n"
            "እባክዎን ትክክለኛ ስልክ ወይም የአካውንት ቁጥር ብቻ ያስገቡ (ምሳሌ: `0935084226`):",
            parse_mode="Markdown"
        )
        # Re-register this step until they enter a valid number
        bot.register_next_step_handler(msg, receive_withdraw_account, method, amount)
        return

    # If number is valid, ask for their Full Name
    msg = bot.send_message(
        message.chat.id,
        f"✅ የ {method} ቁጥር: `{account_info}`\n\n"
        f"👤 እባክዎን የአካውንቱን **ሙሉ ስም (Full Name)** ያስገቡ:-",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, receive_withdraw_fullname, method, amount, account_info)


# Step 5: Receive Full Name, Deduct Firebase Balance, Send User Confirmation & Notify Admin
def receive_withdraw_fullname(message, method, amount, account_info):
    if message.text in ["💼 የኔ ሂሳብ (Account)", "📥 ገቢ (Deposit)", "📤 ወጪ (Withdraw)", "🎁 ጋብዝ እና አትርፍ (Refer)", "🎧 እርዳታ ማእከል (Help & Support)"]:
        bot.send_message(message.chat.id, "ሂደቱ ተቋርጧል። (Process cancelled.)")
        return

    full_name = message.text.strip()
    user_id = str(message.chat.id)

    # 1. Fetch balance from Firebase
    user_ref = db.collection("users").document(user_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        bot.send_message(message.chat.id, "❌ መለያ አልተገኘም። (Account not found.)")
        return

    current_balance = float(user_doc.to_dict().get("balance", 0.0)) - float(user_doc.to_dict().get("bonus", 0.0) or 0.0)   # main wallet only

    blocked = withdraw_block_message(user_doc.to_dict())
    if blocked:
        bot.send_message(message.chat.id, blocked)
        return

    if current_balance < amount:
        bot.send_message(
            message.chat.id, 
            f"❌ በቂ ሂሳብ የለዎትም! (Insufficient funds)\nያለዎት ሂሳብ: **{current_balance:.2f} ETB**", 
            parse_mode="Markdown"
        )
        return

    # 2. Deduct amount from Firebase
    updated_data = process_transaction(user_id, 'withdraw', amount)
    if not updated_data:
        bot.send_message(message.chat.id, "⚠️ ሂሳብዎ ተቀይሯል፣ እባክዎ እንደገና ይሞክሩ። (Balance changed, please try again.)")
        return
    bonus_now = float(updated_data.get('bonus', 0.0) or 0.0)
    new_balance = updated_data.get('balance', 0.0) - bonus_now          # main wallet left after this withdrawal

    # 3. DEFINE user_confirmation BEFORE SENDING
    user_confirmation = (
        f"✅ የ **{amount:g} ETB** የወጪ ጥያቄዎ ለተቆጣጣሪ ተልኳል!\n\n"
        f"📌 **የጥያቄው ዝርዝር:**\n"
        f"• የክፍያ መንገድ: **{method}**\n"
        f"• አካውንት/ስልክ: `{account_info}`\n"
        f"• የባንክ ባለቤት ስም: **{full_name}**\n"
        f"• የቀረ ሂሳብ: **{new_balance:.2f} ETB**"
    )

    # 4. Send confirmation to User
    bot.send_message(message.chat.id, user_confirmation, parse_mode="Markdown")

# 3. Send Request to Admin (Inside receive_withdraw_fullname)
    username = message.from_user.username if message.from_user.username else "No Username"

    admin_msg = (
        "💸 **አዲስ የወጪ ጥያቄ (NEW WITHDRAW REQUEST)**\n\n"
        f"👤 ተጠቃሚ: {message.from_user.first_name} (@{username})\n"
        f"🆔 User ID: `{user_id}`\n"
        f"🏦 ባንክ: **{method}**\n"
        f"💵 መጠን: **{amount:g} ETB**\n"
        f"💰 ቀሪ ሂሳብ: **{new_balance:.2f} ETB** (ከጥያቄው በፊት: {new_balance + amount:.2f}) · 🎁 {bonus_now:.2f}\n"
        f"📱 አካውንት/ስልክ: `{account_info}`\n"
        f"👤 ስም: **{full_name}**"
    )

    markup = types.InlineKeyboardMarkup()
    btn_approve = types.InlineKeyboardButton("✅ ተልኳል (Approve)", callback_data=f"wapp_{user_id}_{amount}")
    # 🟢 Fixed callback_data to 'wrej_' (no middle underscore)
    btn_reject = types.InlineKeyboardButton("❌ ውድቅ አድርግ (Reject)", callback_data=f"wrej_{user_id}_{amount}")
    markup.add(btn_approve, btn_reject)

    bot.send_message(ADMIN_ID, admin_msg, reply_markup=markup, parse_mode="Markdown")


# Step 5: Admin Withdraw Approval & Rejection Decision Handler
@bot.callback_query_handler(func=lambda call: call.data.startswith('wapp_') or call.data.startswith('wrej_'))
def handle_withdraw_admin_decision(call):
    if call.message.chat.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "You are not authorized.")
        return

    # Split: ['wapp'/'wrej', 'USER_ID', 'AMOUNT']
    data = call.data.split('_')
    action = data[0]
    target_user_id = data[1]
    amount = float(data[2])

    if action == "wapp":
        # The withdrawal was already written to history when it was requested (process_transaction),
        # so approving does NOT add a second entry. Rejecting removes that entry again and refunds.

        user_confirmation = f"✅ የ **{amount:g}** ETB የወጪ ጥያቄዎ በተቆጣጣሪው ፀድቋል! ገንዘቡ ተልኮልዎታል::"
        new_text = f"{call.message.text}\n\n✅ **STATUS: APPROVED**"

        bot.send_message(target_user_id, user_confirmation, parse_mode="Markdown")
        bot.edit_message_text(
            new_text,
            chat_id=ADMIN_ID,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id, "Withdrawal approved!")

    elif action == "wrej":
        # 🟢 Refund the balance directly in Firebase Firestore
        user_ref = db.collection("users").document(str(target_user_id))
        user_doc = user_ref.get()

        if user_doc.exists:
            user_data = user_doc.to_dict()
            current_balance = user_data.get('balance', 0.0)

            # 1. Get the current transaction history array
            current_history = user_data.get('transactions', [])

            # 2. Filter out the pending withdrawal
            withdrawal_removed = False
            updated_history = []

            for tx in reversed(current_history):
                if not withdrawal_removed and tx.get('type') == 'withdraw' and float(tx.get('amount', 0)) == float(amount):
                    withdrawal_removed = True
                    continue  # Skip adding this transaction to delete it
                updated_history.append(tx)

            updated_history.reverse()

            # 3. Update Firestore with refunded balance and cleaned history
            user_ref.update({
                "balance": current_balance + amount,
                "transactions": updated_history
            })
            try:
                wallet.cache_drop(target_user_id)
            except Exception:
                pass

        user_confirmation = f"❌ የ **{amount:g}** ETB የወጪ ጥያቄዎ ውድቅ ተደርጓል! ብሩ ወደ መለያዎ ተመልሷል።"
        new_text = f"{call.message.text}\n\n❌ **STATUS: REJECTED & REFUNDED**"

        bot.send_message(target_user_id, user_confirmation, parse_mode="Markdown")
        bot.edit_message_text(
            text=new_text,
            chat_id=ADMIN_ID,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id, "Withdrawal rejected and refunded.")

    # Remove buttons from admin chat
    if 'new_text' in locals():
        bot.edit_message_text(text=new_text, chat_id=ADMIN_ID, message_id=call.message.message_id, parse_mode="Markdown")
# ==========================================
# 🎁REFERRAL SYSTEM BUTTON LOGIC
# ==========================================
@bot.message_handler(func=lambda message: message.text == "🎁 ጋብዝ እና አግኝ (Refer)")
def show_referral_info(message):
    user_id = message.chat.id
    bot_username = bot.get_me().username
    
    # 🔗 Generate unique deep-link for this user
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    # Fetch user referral stats from Firestore
    doc = db.collection("users").document(str(user_id)).get()
    data = doc.to_dict() if doc.exists else {}
    ref_count = data.get("referrals_count", 0)
    ref_earnings = data.get("referral_earnings", 0.0)
    inviter_bonus, newcomer_bonus = get_bonus_amounts()
    
    msg = (
        "🎁 **የመጋበዣ ሊንክ (Referral System)**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "ጓደኞችዎን ይጋብዙ እና በእያንዳንዱ በሚቀላቀሉት ጓደኛ ቦነስ ያግኙ!\n\n"
        f"💵 እርስዎ **{inviter_bonus:g} ETB**፣ ጓደኛዎ ደግሞ **{newcomer_bonus:g} ETB** ያገኛሉ!\n\n"
        f"🔗 **የእርስዎ መጋበዣ ሊንክ:**\n`{ref_link}`\n\n"
        f"👥 **የጋበዟቸው ሰዎች:** {ref_count}\n"
        f"💰 **ያገኙት ቦነስ:** {ref_earnings:.2f} ETB\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💡 *ሊንኩን ኮፒ በማድረግ ለጓደኞችዎ ያጋሩ!*"
    )
    bot.send_message(user_id, msg, parse_mode="Markdown")
# ==========================================
# 📣 ADMIN ONLY: /broadcast (send any message to every user) and /stats
# ==========================================
_pending_broadcast = {}
_broadcast_running = False

def _all_user_ids():
    """Every user id (ids only, so it is cheap)."""
    return [d.id for d in db.collection("users").select([]).stream() if d.id.isdigit()]

@bot.message_handler(commands=['stats'])
def admin_stats(message):
    if message.from_user.id != ADMIN_ID:
        return
    bot.send_message(message.chat.id, f"👥 ጠቅላላ ተጠቃሚዎች: {len(_all_user_ids())}")

@bot.message_handler(commands=['broadcast'])
def admin_broadcast_start(message):
    if message.from_user.id != ADMIN_ID:
        return
    bot.clear_step_handler_by_chat_id(message.chat.id)
    msg = bot.send_message(
        message.chat.id,
        "📣 ለሁሉም ተጠቃሚዎች የሚላከውን መልእክት አሁን ይላኩ (ጽሑፍ፣ ፎቶ ወይም ቪዲዮ ሊሆን ይችላል)።\n\nለመሰረዝ /cancel ይጻፉ።"
    )
    bot.register_next_step_handler(msg, admin_broadcast_preview)

def admin_broadcast_preview(message):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text and message.text.startswith("/"):        # /cancel or any other command = cancel
        bot.send_message(message.chat.id, "❌ ተሰርዟል።")
        return
    total = len(_all_user_ids())
    _pending_broadcast[message.from_user.id] = (message.chat.id, message.message_id)
    bot.send_message(message.chat.id, "👇 ተጠቃሚዎች የሚያዩት መልእክት ይህ ነው:")
    bot.copy_message(message.chat.id, message.chat.id, message.message_id)
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(f"✅ ለ {total} ተጠቃሚዎች ላክ", callback_data="bc_send"),
        types.InlineKeyboardButton("❌ ሰርዝ", callback_data="bc_cancel"),
    )
    bot.send_message(message.chat.id, "ይህ መልእክት ለሁሉም ይላክ?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ("bc_send", "bc_cancel"))
def admin_broadcast_confirm(call):
    global _broadcast_running
    bot.answer_callback_query(call.id)
    if call.from_user.id != ADMIN_ID:
        return
    try:                                                      # remove the buttons so it can't be sent twice
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    pending = _pending_broadcast.pop(call.from_user.id, None)
    if call.data == "bc_cancel" or not pending:
        bot.send_message(call.message.chat.id, "❌ ተሰርዟል።")
        return
    if _broadcast_running:
        bot.send_message(call.message.chat.id, "⏳ ሌላ መልእክት እየተላከ ነው፣ እባክዎን ይጠብቁ።")
        return
    _broadcast_running = True
    bot.send_message(call.message.chat.id, "🚀 መላክ ተጀምሯል... ሲጨርስ ሪፖርት እልካለሁ።")
    Thread(target=_run_broadcast, args=(pending[0], pending[1], call.message.chat.id), daemon=True).start()

def _run_broadcast(src_chat, src_msg, admin_chat):
    global _broadcast_running
    sent = failed = 0
    try:
        for uid in _all_user_ids():
            for attempt in (1, 2):
                try:
                    bot.copy_message(int(uid), src_chat, src_msg)   # copies text, photos, videos, formatting
                    sent += 1
                    break
                except Exception as e:
                    retry = ((getattr(e, "result_json", None) or {}).get("parameters") or {}).get("retry_after")
                    if retry and attempt == 1:                     # Telegram says "slow down": wait, try once more
                        time.sleep(int(retry) + 1)
                        continue
                    failed += 1                                    # blocked the bot, deleted account, etc.
                    break
            time.sleep(0.05)                                       # about 20 messages per second
    finally:
        _broadcast_running = False
        try:
            bot.send_message(admin_chat, f"✅ ተልኳል: {sent}\n❌ አልደረሰም: {failed}")
        except Exception:
            pass

# <<ADMIN-SETTINGS-BEGIN>>
MAX_BONUS = 100.0     # safety limit per person, so a typo like /setbonus 1000 500 can't be saved

@bot.message_handler(commands=['admin'])
def admin_help(message):
    if message.from_user.id != ADMIN_ID:
        return
    bot.send_message(
        message.chat.id,
        "🛠 የአድሚን ትዕዛዞች:\n\n"
        "/broadcast — ለሁሉም ተጠቃሚዎች መልእክት ላክ\n"
        "/stats — ጠቅላላ ተጠቃሚዎች\n"
        "/top — ከፍተኛ 10 ጋባዦች\n"
        "/bonus — የአሁኑን የግብዣ ቦነስ አሳይ\n"
        "/setbonus 10 5 — ቦነስ ቀይር (መጀመሪያ ጋባዥ፣ ቀጥሎ አዲስ ተጠቃሚ)\n"
        "/winalerts — የአሸናፊ መልእክት (on / off / ዝቅተኛ ሽልማት)\n"
        "/user @username — የተጠቃሚ ሂሳብ እና ታሪክ\n"
        "/depositbonus 100 — የተቀማጭ ቦነስ አብራ (off = አጥፋ)\n"
        "/rich — ከ200 ETB በላይ ያላቸው ተጫዋቾች"
    )

@bot.message_handler(commands=['bonus'])
def admin_bonus_show(message):
    if message.from_user.id != ADMIN_ID:
        return
    inviter, newcomer = get_bonus_amounts()
    bot.send_message(
        message.chat.id,
        f"🎁 አሁን ያለው የግብዣ ቦነስ:\n👤 ጋባዥ: {inviter:g} ETB\n🆕 አዲስ ተጠቃሚ: {newcomer:g} ETB\n\n"
        "ለመቀየር: /setbonus 10 5\n(መጀመሪያ ለጋባዥ፣ ቀጥሎ ለአዲስ ተጠቃሚ)"
    )

@bot.message_handler(commands=['setbonus'])
def admin_bonus_set(message):
    if message.from_user.id != ADMIN_ID:
        return
    usage = ("ትክክለኛ አጻጻፍ: /setbonus 10 5\n"
             "(መጀመሪያ ለጋባዥ፣ ቀጥሎ ለአዲስ ተጠቃሚ — በ ETB)\n0 ማለት ያንን ቦነስ ማጥፋት ነው።")
    parts = (message.text or "").split()[1:]
    if len(parts) != 2:
        bot.send_message(message.chat.id, usage)
        return
    try:
        inviter, newcomer = float(parts[0]), float(parts[1])
    except ValueError:
        bot.send_message(message.chat.id, usage)
        return
    if not (0 <= inviter <= MAX_BONUS and 0 <= newcomer <= MAX_BONUS):    # also rejects nan / inf
        bot.send_message(message.chat.id, f"⚠️ ቁጥሮቹ ከ0 እስከ {MAX_BONUS:g} መካከል መሆን አለባቸው።")
        return
    db.collection("settings").document("bonus").set({
        "referrer": inviter,
        "newcomer": newcomer,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    })
    bot.send_message(
        message.chat.id,
        f"✅ ተቀምጧል!\n👤 ጋባዥ: {inviter:g} ETB\n🆕 አዲስ ተጠቃሚ: {newcomer:g} ETB\n\n"
        "ከአሁን በኋላ ለሚቀላቀሉ ተጠቃሚዎች ይሠራል።"
    )

@bot.message_handler(commands=['top'])
def admin_top_referrers(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        docs = list(db.collection("users")
                    .order_by("referrals_count", direction=firestore.Query.DESCENDING)
                    .limit(10).stream())
    except Exception as e:
        print(f"top referrers error: {e}")
        bot.send_message(message.chat.id, "⚠️ ዝርዝሩን ማምጣት አልተቻለም፣ እንደገና ይሞክሩ።")
        return
    rows = []
    for d in docs:
        u = d.to_dict() or {}
        count = int(u.get("referrals_count", 0) or 0)
        if count <= 0:
            continue
        name = u.get("first_name") or "-"
        handle = f" @{u['username']}" if u.get("username") else ""
        earned = float(u.get("referral_earnings", 0) or 0)
        rows.append(f"{len(rows) + 1}. {name}{handle} (ID {d.id})\n    👥 {count} ጓደኛ · 💰 {earned:g} ETB")
    if not rows:
        bot.send_message(message.chat.id, "እስካሁን ማንም ጓደኛ አልጋበዘም።")
        return
    bot.send_message(message.chat.id, "🏆 ከፍተኛ 10 ጋባዦች\n\n" + "\n".join(rows))
# <<ADMIN-SETTINGS-END>>

##<<WINALERT-BEGIN>>
_winalerts = {"enabled": True, "min": 0.0}      # min = smallest total prize (ETB) worth a message

def load_winalerts():
    try:
        d = db.collection("settings").document("winalerts").get().to_dict() or {}
        _winalerts["enabled"] = bool(d.get("enabled", True))
        _winalerts["min"] = float(d.get("min", 0.0))
    except Exception as e:
        print(f"winalerts: using defaults ({e})")

def _save_winalerts():
    try:
        db.collection("settings").document("winalerts").set(dict(_winalerts))
    except Exception as e:
        print(f"winalerts: could not save ({e})")

def send_win_alert(event):
    """Called by the game engine after every settled round (in its own thread)."""
    if not _winalerts["enabled"]:
        return
    if not event.get("no_winner") and event.get("pool", 0) < _winalerts["min"]:
        return
    if event.get("no_winner"):
        text = "⚠️ አሸናፊ አልተገኘም — ክፍያው ተመልሷል።"
    else:
        winners = event.get("winners", [])
        lines = []
        for w in winners[:15]:
            who = f"@{w['username']}" if w.get("username") else f"{w.get('name') or '-'} (ID {w.get('uid')})"
            lines.append(f"🏆 {who} — {w.get('prize', 0):g} ETB")
        if len(winners) > 15:
            lines.append(f"... እና ሌሎች {len(winners) - 15}")
        text = "\n".join(lines)
    try:
        bot.send_message(ADMIN_ID, text)
    except Exception as e:
        print(f"winalerts: could not send ({e})")

@bot.message_handler(commands=['winalerts'])
def admin_winalerts(message):
    if message.from_user.id != ADMIN_ID:
        return
    usage = ("/winalerts on — ሁሉንም ዙር አሳውቅ\n"
             "/winalerts off — አጥፋ\n"
             "/winalerts 50 — ሽልማቱ 50 ETB እና ከዚያ በላይ የሆኑትን ብቻ አሳውቅ\n"
             "/winalerts 0 — ሁሉንም ዙር አሳውቅ")
    parts = (message.text or "").split()[1:]
    if parts:
        a = parts[0].lower()
        if a == "on":
            _winalerts["enabled"] = True
        elif a == "off":
            _winalerts["enabled"] = False
        else:
            try:
                v = float(a)
            except ValueError:
                bot.send_message(message.chat.id, usage)
                return
            if not (0 <= v <= 100000):                    # also rejects nan / inf
                bot.send_message(message.chat.id, usage)
                return
            _winalerts["min"] = v
            _winalerts["enabled"] = True
        _save_winalerts()
    state = "በርቷል ✅" if _winalerts["enabled"] else "ጠፍቷል ⛔"
    bot.send_message(message.chat.id,
                     f"🔔 የአሸናፊ መልእክት: {state}\nዝቅተኛ ሽልማት: {_winalerts['min']:g} ETB\n\n{usage}")
# <<WINALERT-END>>

# <<ADMIN-LOOKUP-BEGIN>>
def _tx_totals(u):
    t = {"deposit": 0.0, "withdraw": 0.0, "win": 0.0, "bonus": 0.0}
    for x in u.get("transactions") or []:
        if x.get("type") in t:
            t[x["type"]] += float(x.get("amount", 0) or 0)
    return t

def _who(uid, u):
    return f"@{u['username']}" if u.get("username") else f"{u.get('first_name') or '-'} (ID {uid})"

@bot.message_handler(commands=['user'])
def admin_user_lookup(message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = (message.text or "").split()[1:]
    if not parts:
        bot.send_message(message.chat.id, "ትክክለኛ አጻጻፍ:\n/user @username\n/user 123456789")
        return
    q = parts[0].lstrip("@").strip()
    doc = None
    try:
        if q.isdigit():
            d = db.collection("users").document(q).get()
            doc = d if d.exists else None
        else:
            for name in dict.fromkeys([q, q.lower()]):
                found = list(db.collection("users").where("username", "==", name).limit(1).stream())
                if found:
                    doc = found[0]
                    break
    except Exception as e:
        print(f"user lookup error: {e}")
        bot.send_message(message.chat.id, "⚠️ ማምጣት አልተቻለም፣ እንደገና ይሞክሩ።")
        return
    if doc is None:
        bot.send_message(message.chat.id, "ተጠቃሚው አልተገኘም።")
        return
    u = doc.to_dict() or {}
    t = _tx_totals(u)
    status = "🔒 ወጪ መጠየቅ አይችልም (ከቦነስ በኋላ ገቢ አላደረገም)" if withdraw_block_message(u) else "✅ ወጪ መጠየቅ ይችላል"
    bot.send_message(message.chat.id,
        f"👤 {_who(doc.id, u)} (ID {doc.id})\n📞 {u.get('phone_number') or '-'}\n\n"
        f"💰 ዋና: {float(u.get('balance', 0) or 0) - float(u.get('bonus', 0) or 0):.2f} ETB · 🎁 ጨዋታ: {float(u.get('bonus', 0) or 0):.2f} ETB\n"
        f"⬇️ ገቢ: {t['deposit']:g} · ⬆️ ወጪ: {t['withdraw']:g}\n"
        f"🏆 ድል: {t['win']:g} · 🎁 ቦነስ: {t['bonus']:g}\n"
        f"🎮 ጨዋታዎች: {int(u.get('total_games_played', 0) or 0)} · 👥 ጋብዟል: {int(u.get('referrals_count', 0) or 0)}\n\n{status}")

@bot.message_handler(commands=['rich'])
def admin_rich(message):
    """Top players holding more than 200 ETB (or /rich 500) who are free to withdraw, i.e. not bonus-locked.
    Costs at most 40 Firestore reads per use."""
    if message.from_user.id != ADMIN_ID:
        return
    parts = (message.text or "").split()[1:]
    minimum = 200.0
    if parts:
        try:
            minimum = float(parts[0])
        except ValueError:
            bot.send_message(message.chat.id, "ትክክለኛ አጻጻፍ: /rich  ወይም  /rich 500")
            return
    try:
        docs = list(db.collection("users").where("balance", ">", minimum)
                    .order_by("balance", direction=firestore.Query.DESCENDING).limit(40).stream())
    except Exception as e:
        print(f"rich error: {e}")
        bot.send_message(message.chat.id, "⚠️ ዝርዝሩን ማምጣት አልተቻለም፣ እንደገና ይሞክሩ።")
        return
    ranked = []
    for d in docs:
        u = d.to_dict() or {}
        main = float(u.get('balance', 0) or 0) - float(u.get('bonus', 0) or 0)       # bonus (play wallet) is not counted
        if main > minimum:
            ranked.append((main, d.id, u))
    ranked.sort(key=lambda r: r[0], reverse=True)
    rows = [f"{i}. {_who(uid, u)} — {main:.2f} ETB (ገቢ {_tx_totals(u)['deposit']:g})" + (" 🔒" if withdraw_block_message(u) else "")
            for i, (main, uid, u) in enumerate(ranked[:10], 1)]
    text = f"💎 ዋና ሂሳብ ከ{minimum:g} ETB በላይ ያላቸው\n\n" + ("\n".join(rows) if rows else "ማንም የለም።")
    if any(" 🔒" in r for r in rows):
        text += "\n\n🔒 = ከቦነስ በኋላ ገቢ አላደረገም (ወጪ መጠየቅ አይችልም)"
    bot.send_message(message.chat.id, text)
# <<ADMIN-LOOKUP-END>>

# <<DEPOSITBONUS-BEGIN>>
# 🎁 Deposit-bonus campaigns. The bonus goes to the PLAY wallet when you approve a deposit.
# Settings live in memory (one read at startup, one write per change).
_depositbonus = {"enabled": False, "percent": 100.0, "cap": 0.0}          # cap 0 = no cap per deposit
MAX_DEPOSIT_PERCENT = 300.0

def load_depositbonus():
    try:
        d = db.collection("settings").document("depositbonus").get().to_dict() or {}
        _depositbonus.update(enabled=bool(d.get("enabled", False)), percent=float(d.get("percent", 100.0)), cap=float(d.get("cap", 0.0)))
    except Exception as e:
        print(f"depositbonus: using defaults ({e})")

def _save_depositbonus():
    try:
        db.collection("settings").document("depositbonus").set(dict(_depositbonus))
    except Exception as e:
        print(f"depositbonus: could not save ({e})")

def deposit_bonus_for(amount):
    """Bonus (ETB) for a deposit of `amount` under the current campaign; 0 when no campaign is on."""
    if not _depositbonus["enabled"] or amount <= 0:
        return 0.0
    bonus = amount * _depositbonus["percent"] / 100.0
    if _depositbonus["cap"] > 0:
        bonus = min(bonus, _depositbonus["cap"])
    return round(bonus, 2)

def deposit_offer_line(amount):
    b = deposit_bonus_for(amount)
    return f"🎁 የተቀማጭ ቦነስ አለ! በዚህ ገቢ {b:g} ETB ቦነስ ያገኛሉ።\n\n" if b > 0 else ""

def deposit_bonus_announcement():
    pct, cap = _depositbonus["percent"], _depositbonus["cap"]
    b = deposit_bonus_for(100)
    text = (f"🔥 የተቀማጭ ቦነስ ተጀምሯል! 🔥\n\nአሁን ገቢ (Deposit) ሲያደርጉ {pct:g}% ቦነስ ያገኛሉ!\n\n"
            f"ለምሳሌ 100 ብር ሲያስገቡ:\n💰 100 ብር → ወደ ዋና ሂሳብዎ\n🎁 {b:g} ብር ቦነስ → ወደ የጨዋታ ሂሳብዎ\n")
    if cap > 0:
        text += f"\n(በአንድ ገቢ ቢበዛ {cap:g} ብር ቦነስ)\n"
    return text + "\n👉 አሁኑኑ ገቢ ያድርጉ እና ይጫወቱ!"

@bot.message_handler(commands=['depositbonus'])
def admin_depositbonus(message):
    if message.from_user.id != ADMIN_ID:
        return
    usage = ("/depositbonus 100 — 100% ቦነስ አብራ\n/depositbonus 100 200 — 100%፣ በአንድ ገቢ ቢበዛ 200 ብር\n"
             "/depositbonus off — አጥፋ\n/depositbonus on — በቀድሞው መጠን አብራ")
    parts = (message.text or "").split()[1:]
    announce = False
    if parts:
        a = parts[0].lower()
        if a == "off":
            _depositbonus["enabled"] = False
        elif a == "on":
            _depositbonus["enabled"] = True
            announce = True
        else:
            try:
                pct = float(a)
                cap = float(parts[1]) if len(parts) > 1 else 0.0
            except ValueError:
                bot.send_message(message.chat.id, usage)
                return
            if not (0 < pct <= MAX_DEPOSIT_PERCENT) or not (0 <= cap <= 100000):          # also rejects nan / inf
                bot.send_message(message.chat.id, f"⚠️ መቶኛው ከ1 እስከ {MAX_DEPOSIT_PERCENT:g} መሆን አለበት።\n\n{usage}")
                return
            _depositbonus.update(enabled=True, percent=pct, cap=cap)
            announce = True
        _save_depositbonus()
    on = _depositbonus["enabled"]
    state = (f"በርቷል ✅ — {_depositbonus['percent']:g}%" + (f" (በአንድ ገቢ ቢበዛ {_depositbonus['cap']:g} ብር)" if _depositbonus["cap"] > 0 else "")) if on else "ጠፍቷል ⛔"
    bot.send_message(message.chat.id, f"🎁 የተቀማጭ ቦነስ: {state}\n\n{usage}")
    if announce and on:                       
        preview = bot.send_message(message.chat.id, deposit_bonus_announcement())
        _pending_broadcast[message.from_user.id] = (message.chat.id, preview.message_id)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ ለሁሉም ላክ", callback_data="bc_send"), types.InlineKeyboardButton("❌ አይላክ", callback_data="bc_cancel"))
        bot.send_message(message.chat.id, "👆 ይህ ማስታወቂያ ለሁሉም ተጠቃሚዎች ይላክ?", reply_markup=markup)

def game_rules_text():
    return (
f"🎱 የጨዋታው ህጎች\n\n"
f"1️⃣ ካርቴላ መምረጥ\n"
f"• ከ1 እስከ 500 ካሉት ካርቴላዎች ይምረጡ። እያንዳንዱ ካርቴላ የራሱ ቁጥሮች ያሉት የቢንጎ ካርድ ነው።\n"
f"• የአንድ ካርቴላ ዋጋ {TICKET_PRICE:g} ብር ነው፤ በአንድ ዙር ቢበዛ {MAX_SELECTION} ካርቴላ።\n"
f"• አንድ ካርቴላ በአንድ ዙር ለአንድ ተጫዋች ብቻ ይሰጣል። የተመረጠ ካርቴላ ለሌሎች ግራጫ ሆኖ ይታያል።\n"
f"• ምርጫው በ{engine.selection_seconds} ሰከንድ ቆጣሪ ውስጥ ነው፤ ጊዜው ሳያልቅ መቀየር ይችላሉ።\n\n"
f"2️⃣ ሁለቱ ሂሳቦች\n"
f"• ዋና ሂሳብ፦ ገቢ ያደረጉት ገንዘብ እና ያሸነፉት ሽልማት። ወጪ መጠየቅ የሚቻለው ከዚህ ሂሳብ ብቻ ነው።\n"
f"• የጨዋታ ሂሳብ፦ ቦነስ (የግብዣ እና የተቀማጭ ቦነስ)። ለመጫወት ብቻ ነው፤ ሊወጣ አይችልም።\n"
f"• ካርቴላ ሲመርጡ መጀመሪያ ከጨዋታ ሂሳብ፣ ከዚያ ከዋና ሂሳብ ይቆረጣል። ገንዘቡ የሚቆረጠው ምርጫው ሲዘጋ (ጨዋታው ሲጀምር) ብቻ ነው፤ ከዚያ በፊት ምርጫዎን ከሰረዙ ምንም አይቆረጥም።\n\n"
f"3️⃣ ጨዋታው መጀመር\n"
f"• ቢያንስ {engine.min_players} ተጫዋቾች ሲመርጡ ጨዋታው ይጀምራል። በቂ ተጫዋች ከሌለ ቆጣሪው ይጠብቃል፤ ምንም ገንዘብ አይቆረጥም።\n"
f"• ሁሉም ተጫዋቾች በአንድ ዙር በተመሳሳይ ሰዓት ይጫወታሉ።\n\n"
f"4️⃣ ቁጥር መጥራት\n"
f"• በየ{engine.draw_interval:g} ሰከንዱ አንድ ቁጥር (ከ1 እስከ 75) በድምፅ ይጠራል። ቁጥሮቹ በሲስተሙ በዘፈቀደ ይወጣሉ፤ አንድ ቁጥር ሁለት ጊዜ አይወጣም።\n"
f"• B (1–15)፣ I (16–30)፣ N (31–45)፣ G (46–60)፣ O (61–75)። የወጡ ቁጥሮች በካርዱ ላይ በራስ-ሰር ምልክት ይደረግባቸዋል።\n\n"
f"5️⃣ እንዴት ያሸንፋሉ\n"
f"ከሚከተሉት አንዱን ቀድሞ የሞላ ካርቴላ ያሸንፋል፦\n"
f"• ሙሉ አግድም መስመር • ሙሉ ቀጥ ያለ መስመር • ሰያፍ መስመር (ሁለቱም አቅጣጫ) • አራቱ ማዕዘኖች\n"
f"የካርዱ መሃል ነፃ (FREE) ነው። ቢንጎውን ሲስተሙ በራሱ ያረጋግጣል፤ ምንም ቁልፍ መጫን አያስፈልግም።\n\n"
f"6️⃣ ሽልማት\n"
f"• ከእያንዳንዱ የተመረጠ ካርቴላ {PRIZE_PER_CARTEL:g} ብር ወደ ሽልማቱ ይገባል (ከ{TICKET_PRICE:g} ብር {TICKET_PRICE - PRIZE_PER_CARTEL:g} ብሩ የአገልግሎት ክፍያ ነው)። ብዙ ካርቴላዎች በአንድ ቁጥር ካሸነፉ ሽልማቱ እኩል ይካፈላል።\n"
f"• ሽልማቱ ወዲያውኑ በራስ-ሰር ወደ ሂሳብዎ ይገባል። ከዋና ሂሳብ ባስያዙት ክፍል የሚገኘው ወደ ዋና ሂሳብ፣ ከጨዋታ ሂሳብ (ቦነስ) ባስያዙት ክፍል የሚገኘው ወደ የጨዋታ ሂሳብ ይገባል።\n"
f"• ውጤቱ ለ{engine.result_seconds} ሰከንድ ከታየ በኋላ አዲስ ዙር በራሱ ይጀምራል።\n\n"
f"7️⃣ ቦነስ\n"
f"• ጓደኛ ሲጋብዙ እርስዎ እና ጓደኛዎ ቦነስ ያገኛሉ (መጠኑ በ\"ጋብዝ\" ክፍል ይታያል)።\n"
f"• ከጊዜ ወደ ጊዜ የተቀማጭ ቦነስ ዘመቻ ይኖራል፤ ዘመቻው ሲኖር ገቢ ሲያደርጉ ቦነሱ ወደ የጨዋታ ሂሳብዎ ይጨመራል።\n\n"
f"8️⃣ ገቢ ማድረግ\n"
f"• በTelebirr ወይም CBE Birr ገቢ ያድርጉ፣ ከዚያ ሙሉውን የክፍያ መልእክት (text) ወይም ስክሪንሾት ይላኩ።\n"
f"• መልእክቱ ወደ ተሰጠው አካውንት የተላከ እና ከገቡት መጠን ጋር የሚመሳሰል መሆን አለበት። አንድ ደረሰኝ አንድ ጊዜ ብቻ ይሠራል።\n\n"
f"9️⃣ ወጪ ማድረግ\n"
f"• ወጪ መጠየቅ የሚቻለው ከዋና ሂሳብ ብቻ ነው፤ ቢያንስ 100 ብር ሊኖርዎ ይገባል።\n"
f"• የግብዣ ቦነስ ያገኙ ተጫዋቾች ወጪ ከመጠየቃቸው በፊት ቢያንስ አንድ ጊዜ ገቢ ማድረግ አለባቸው።\n"
f"• ጥያቄዎ በተቻለ ፍጥነት ይፈጸማል።\n\n"
f"🔟 ችግር ቢፈጠር\n"
f"• በሲስተም ችግር ጨዋታው ከተቋረጠ የዙሩ ክፍያ ሙሉ በሙሉ ወደ ሂሳብዎ ይመለሳል።\n\n"
f"⚠️ ማጭበርበር ወይም ቦነስ ለማግኘት ብዙ አካውንት መክፈት የተከለከለ ነው፤ አካውንቱ ሊታገድ ይችላል። ጨዋታው ዕድሜያቸው 18 እና ከዚያ በላይ ለሆኑ ብቻ ነው። ከአቅምዎ በላይ አይጫወቱ።"
    )

@bot.message_handler(commands=['rules'])
def user_rules(message):
    bot.send_message(message.chat.id, game_rules_text())
# <<DEPOSITBONUS-END>>

@bot.message_handler(commands=['clear'])
def clear_keyboard(message):
    # This completely deletes any sticky bottom keyboards
    remove_markup = types.ReplyKeyboardRemove()
    bot.send_message(message.chat.id, "🧹 የድሮው ሰሌዳ ፀድቷል (Old keyboard cleared)", reply_markup=remove_markup)
    # --- FLASK API SERVER FOR WEBAPP FETCH REQUESTS ---
app = Flask(__name__)
CORS(app, origins=[WEBAPP_ORIGIN], allow_headers=["Content-Type", "X-Telegram-Init-Data"], max_age=7200)
@app.route('/')
def serve_webapp():
    return send_file('index.html')

# ==========================================================
# 🎰 SHARED GAME ROUND (one round for every player)
# The server runs the round; the Mini App only displays it and sends picks.
# ==========================================================
wallet = FirestoreWallet(db, firestore)
engine = GameEngine(wallet, min_players=int(os.environ.get("MIN_PLAYERS", "2")))
engine.on_round_result = send_win_alert     # admin message after every round (see /winalerts)

@app.route('/health')
def health():
    """Cheap check for an uptime monitor: it keeps the free Render service awake, and answers 503 if the game engine has died."""
    alive = engine._thread is not None and engine._thread.is_alive()
    return jsonify({"status": "ok" if alive else "engine_down"}), (200 if alive else 503)

_rate = defaultdict(deque)

def _rate_ok(uid, limit=8, per=1.0):
    """Tiny in-memory limiter so one client can't hammer the database."""
    now = time.time()
    q = _rate[uid]
    while q and now - q[0] > per:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True

def _round_reply(ok, code):
    try:
        balance, bonus = wallet.get_wallets(g.tg_user_id)       # from memory; one read at most per player per hour
    except Exception:
        balance, bonus = None, None
    return jsonify({"status": "success" if ok else "error", "code": code,
                    "state": engine.get_state(g.tg_user_id), "balance": balance, "bonus": bonus}), 200

@app.route('/api/round', methods=['GET'])
@require_telegram_auth
def api_round():
    if not _rate_ok(g.tg_user_id):
        return jsonify({"status": "error", "code": "slow_down"}), 429
    return _round_reply(True, "ok")

@app.route('/api/round/pick', methods=['POST'])
@require_telegram_auth
def api_round_pick():
    if not _rate_ok(g.tg_user_id):
        return jsonify({"status": "error", "code": "slow_down"}), 429
    data = request.get_json(force=True, silent=True) or {}
    ok, code = engine.pick(g.tg_user_id, data.get("cartel"))
    return _round_reply(ok, code)

@app.route('/api/round/unpick', methods=['POST'])
@require_telegram_auth
def api_round_unpick():
    if not _rate_ok(g.tg_user_id):
        return jsonify({"status": "error", "code": "slow_down"}), 429
    data = request.get_json(force=True, silent=True) or {}
    cartel = data.get("cartel")
    if not isinstance(cartel, int) or isinstance(cartel, bool):
        return _round_reply(False, "invalid")
    ok, code = engine.unpick(g.tg_user_id, cartel)
    return _round_reply(ok, code)

# (Removed) /api/transaction: balances must never be changed by a client request.
# Deposits/withdrawals go through the bot; game money moves inside the server.

import os

def run_flask_server():
    # Fetch dynamic port assigned by Render, defaulting to 5500 for local testing
    port = int(os.environ.get("PORT", 5500))
    # host='0.0.0.0' allows external web traffic to reach your Flask API
    app.run(host='0.0.0.0', port=port)

@app.route('/api/user-data', methods=['GET'])
@require_telegram_auth
def get_user_data():
    # The caller is identified by Telegram's signed initData, never by a ?userId= value.
    user_id = g.tg_user_id
    try:
        user_doc = db.collection('users').document(user_id).get()
        data = user_doc.to_dict() if user_doc.exists else {}
        wallet.cache_set(user_id, float(data.get("balance", 0) or 0), float(data.get("bonus", 0) or 0))
        return jsonify({
            "status": "success",
            "balance": data.get("balance", 0),
            "bonus": data.get("bonus", 0),
            "transactions": data.get("transactions", []),
            "phone_number": data.get("phone_number"),
            "first_name": data.get("first_name"),
            "total_games_played": data.get("total_games_played", 0),
            "total_winnings": data.get("total_winnings", 0.0),
        }), 200
    except Exception as e:
        print(f"user-data error: {e}")
        return jsonify({"status": "error", "message": "Server error"}), 500

_lb_cache = {"at": 0.0, "data": None}
LEADERBOARD_TTL = 300      # seconds: one Firestore lookup (10 reads) serves every player

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    if _lb_cache["data"] is not None and time.time() - _lb_cache["at"] < LEADERBOARD_TTL:
        return jsonify({'status': 'success', 'leaderboard': _lb_cache["data"]}), 200
    try:
        users_ref = db.collection('users')
       
        query = users_ref.order_by('weekly_cartels', direction=firestore.Query.DESCENDING).limit(10)
        results = query.stream()

        leaderboard = []
        for doc in results:
            data = doc.to_dict()
            leaderboard.append({
                "name": data.get("username") or data.get("first_name") or "Unknown Player",
                "cartels": data.get("weekly_cartels", 0)
            })

        # Pad with empty slots if there are less than 10 users
        while len(leaderboard) < 10:
            leaderboard.append({"name": "---", "cartels": 0})

        _lb_cache["data"], _lb_cache["at"] = leaderboard, time.time()
        return jsonify({'status': 'success', 'leaderboard': leaderboard}), 200

    except Exception as e:
        print(f"Leaderboard Error: {e}")
        if _lb_cache["data"] is not None:         # database trouble: show the last list instead of an error
            return jsonify({'status': 'success', 'leaderboard': _lb_cache["data"]}), 200
        return jsonify({'status': 'error', 'message': 'Failed to load leaderboard'}), 500

@app.route('/api/reset-weekly', methods=['POST'])
def trigger_weekly_reset():
    # Send the secret in the X-Reset-Token header (value = RESET_TOKEN env variable).
    supplied = request.headers.get('X-Reset-Token', '')
    if not RESET_TOKEN or not hmac.compare_digest(supplied.encode(), RESET_TOKEN.encode()):
        return jsonify({"status": "unauthorized"}), 401

    try:
        users_ref = db.collection('users')
        users = users_ref.stream()
        
        batch = db.batch()
        count = 0
        
        for user in users:
            batch.update(user.reference, {'weekly_cartels': 0})
            count += 1
            
            # Firestore limits batch updates to 500 per batch
            if count == 500:
                batch.commit()
                batch = db.batch()
                count = 0
                
        if count > 0:
            batch.commit()
            
        return jsonify({"status": "success", "message": "Leaderboard reset successfully"}), 200

    except Exception as e:
        print(f"Error resetting leaderboard: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

    # --- PLACE API ROUTE HERE (Near other @app.route endpoints) ---
# (Removed) /api/update_stats: stats will be updated by the server when a round is settled.
    # Handle text menu click: "🎧 እርዳታ ማዕከል (Help & Support)"
# 1. Text Button Handler
# Handle text menu click: "🎧 እርዳታ ማዕከል (Help & Support)"
@bot.message_handler(func=lambda message: message.text and 'እርዳታ ማዕከል' in message.text)
def handle_help_support(message):
    support_text = (
        "🎧 **የእርዳታ ማዕከል (Help & Support)**\n\n"
        "ማንኛውም ችግር ወይም ጥያቄ ካለዎት እባክዎ በቀጥታ የድጋፍ ቡድናችንን ያነጋግሩ:\n\n"
        "📩 @zeid369\n"
        "📩 @Theid369"
    )
    bot.send_message(message.chat.id, support_text, parse_mode="Markdown")

# 2. WebApp API Endpoint
@app.route('/api/send-support', methods=['POST'])
@require_telegram_auth
def api_send_support():
    user_id = g.tg_user_id

    # Updated to match the exact formatting of your text handler
    support_text = (
        "🎧 **የእርዳታ ማዕከል (Help & Support)**\n\n"
        "ማንኛውም ችግር ወይም ጥያቄ ካሎት እባክዎ በቀጥታ የድጋፍ ቡድናችንን ያነጋግሩ፡\n\n"
        "📩 @zeid369\n"
        "📩 @Theid369"
    )
    try:
        # Telegram requires the ID to be an integer
        bot.send_message(int(user_id), support_text, parse_mode="Markdown")
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print("Error sending support:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/send-rules', methods=['POST'])
@require_telegram_auth
def send_rules():
    user_id = g.tg_user_id
    
    rules_text = game_rules_text()
    try:
        bot.send_message(chat_id=user_id, text=rules_text)
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Error sending rules: {e}")
        return jsonify({"status": "error"}), 500

# --------------------------------------------------
if __name__ == "__main__":
    print("🤖 1X Bingo Bot is starting...")
    
    load_winalerts()
    load_depositbonus()

    # Start the shared game engine (exactly one per deployment)
    engine.start()

    # Start Flask API in a background thread
    Thread(target=run_flask_server, daemon=True).start()
    print("🌐 WebApp API running on port 5500!")
    
    print("Bot is now running! Press Ctrl+C to stop.")
    bot.infinity_polling()