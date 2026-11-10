TELEGRAM BINGO — UPDATED BUILD

Implemented flows
- Mandatory Telegram channel join before registration; bot checks membership and asks the user to tap Verify after joining.
- Registration is completed only after the user shares their own Telegram contact.
- New users receive the registration bonus (default 10 ETB) in Bonus Balance.
- Referral links use /start=ref_<telegram_id>. When a new invitee joins the required channel and completes phone registration, the referrer receives 20 ETB in Bonus Balance exactly once.
- Bingo ticket charges use Bonus Balance first, then Main Balance.
- Round refunds restore the exact wallet portions that were charged.
- Game winnings are credited to Main Balance (withdrawable/real balance), not Bonus Balance.
- Deposit requests are submitted only inside the Mini App with an amount plus payment reference and/or receipt screenshot; admin approval credits Bonus Balance and sets has_deposited=true.
- Deposits are available immediately after registration; a user does NOT need a previous deposit to submit a deposit request. The deposit is credited only after admin approval.
- Withdrawal requests are submitted only inside the Mini App with amount and Telebirr recipient details. A request reserves the amount from Main Balance; admin rejection refunds it. Admin approval marks it approved, after the admin manually sends the payout externally.
- The bot menu has no Deposit or Withdraw options; those functions are available only as separate pages inside the Mini App.

Render configuration
Build command: npm install
Start command: npm start

Required environment variables:
BOT_TOKEN=<new token from @BotFather>
WEBAPP_URL=https://<your-render-service>.onrender.com
BOT_CHANNEL_ID=-1004418660495
BOT_CHANNEL_URL=https://t.me/test16746g
ADMIN_ID=<main admin Telegram numeric user ID>
ADMIN_IDS=<optional comma-separated additional admin Telegram IDs>
REGISTRATION_BONUS_ETB=10
REFERRAL_BONUS_ETB=20
DEPOSIT_INSTRUCTIONS=💰 Telebirr | አነስተኛ 100 ETB | ስም: Esraeal | አካውንት: 0949196145 | SMS ወይም Screenshot ይላኩ።
SUPPORT_CONTACT=@your_support_username
DEPOSIT_MINIMUM_ETB=100
WITHDRAW_MINIMUM_ETB=100
TELEBIRR_ACCOUNT_NAME=Esraeal
TELEBIRR_ACCOUNT_NUMBER=0949196145
FIREBASE_KEY_PATH=/etc/secrets/firebase_key.json
FIREBASE_DATABASE_URL=https://litebingo-513a9-default-rtdb.firebaseio.com

Firebase Secret File:
Mount the service-account JSON at /etc/secrets/firebase_key.json.
Set FIREBASE_DATABASE_URL=https://litebingo-513a9-default-rtdb.firebaseio.com.
The Admin SDK uses Realtime Database; Firestore is no longer used by this build. Keep this Render service at one instance because the compatibility transaction queue is process-local.
The bot must be an administrator in the required channel so Telegram getChatMember can verify members reliably.
ADMIN_ID must be the main admin Telegram numeric ID. Optional ADMIN_IDS can contain additional comma-separated admin IDs. Admins see an Admin Panel button in the bot menu; open it from Telegram to authenticate with Mini App initData. The admin panel is served at /admin. Deposit and Withdraw open separate pages inside the Mini App and never switch to bot chat. Blocked accounts are denied access to the Mini App APIs and bot commands.

Important operational notes
- A deposit is not credited automatically: an admin must verify the receipt and approve the request.
- An approved withdrawal is a confirmation step; the admin must send the money through the configured external payment method.
- Deposit instructions are configured for Telebirr: Esraeal, 0949196145, minimum 100 ETB. Confirm this account is yours and active before accepting payments; change DEPOSIT_INSTRUCTIONS if needed.
- Do not commit BOT_TOKEN or firebase_key.json to GitHub. Existing Firestore records are not automatically copied into Realtime Database; export/import them separately if you need to preserve them. The previously exposed bot token must be revoked and replaced through @BotFather.
- Users must open the WebApp from the bot. Telegram initData is verified server-side, and API requests also check required channel membership when BOT_CHANNEL_ID is configured.

Deploy and verify
1. Replace the project files in the GitHub repository connected to Render.
2. Confirm all environment variables and the Firebase Secret File above.
3. Deploy with npm install / npm start.
4. Check https://<your-render-service>.onrender.com/health returns {"status":"ok"}.
5. Ensure the bot is an administrator in channel -1004418660495 (@test16746g). Test with a fresh Telegram account: join https://t.me/test16746g -> verify -> share own contact -> receive 10 ETB registration bonus.
6. Test a referral with a second fresh account: complete registration through the inviter link; inviter should receive 20 ETB bonus once.
7. Test deposit request and admin approval; verify Bonus Balance and has_deposited.
8. Test a withdrawal before deposit (must be blocked), then after approved deposit (must create admin review request).
9. Test a round using bonus funds; confirm winnings appear in Main Balance.

Additional reliability fixes in this ZIP
- The WebApp refreshes wallet data at startup and after the round enters drawing/result.
- Telegram channel membership results are cached for 30 seconds per Telegram user to avoid a getChatMember call on every one-second game poll. A failed Telegram check is not cached.
- Paid rounds are recorded in Firebase Realtime Database before drawing begins.
- Before payouts are applied, the complete payout map is saved to Realtime Database. Each user's win credit is idempotent, so a restart can safely finish an interrupted settlement.
- On startup, unfinished locked/drawing rounds are refunded to their charged participants; prepared settlements are resumed. The game engine starts only after recovery completes.
- Deposit and Withdraw are handled inside the Mini App; the bot keyboard no longer exposes either wallet flow.

How to replace the GitHub project from this ZIP
1. Download and extract the ZIP on a computer, or use a ZIP/file manager on Android.
2. Open the extracted XLitebingo-main folder.
3. Upload/replace the project files in the connected GitHub repository. Keep the repository root containing server.js, bot.js, users.js, gameroom.js, index.html and package.json (do not upload the outer folder as a nested project folder).
4. Commit the changes. Render should deploy the new commit automatically; otherwise use Manual Deploy -> Deploy latest commit.
5. Do not upload BOT_TOKEN or firebase_key.json.

Validation
- Node syntax checks passed for server.js, bot.js and users.js; inline JavaScript in index.html and admin.html also passed syntax checks. Static review only; live Render, Telegram and Firebase end-to-end checks still need to be performed after deployment.
- Static review of the recovery and idempotency paths completed.
- Live Render, Telegram and Firebase end-to-end checks still need to be performed after deployment. Test with small amounts first and back up Realtime Database before deployment.

Admin panel additions: separate Main/Bonus balance credit and debit, seven-day transaction summary, deposit/withdrawal review, and Telegram broadcast with audience filters, photo, caption and inline URL button. Deposit accepts a payment reference and/or receipt screenshot in the Mini App; minimum deposit is 100 ETB. Broadcast requires admin Mini App authentication.

Broadcast audience definitions: All = all registered, unblocked users; Verified = users with a saved phone_number from Telegram contact registration; Unverified = users without a saved phone_number. Broadcast supports text-only or JPG/PNG/WEBP photo with caption and optional inline URL button.
Withdrawal: minimum defaults to 100 ETB (WITHDRAW_MINIMUM_ETB). Player supplies recipient name and Telebirr number; request reserves Main Balance. Admin approval is a confirmation only and the payout must be sent manually through Telebirr.
Deposit: admin approval credits Bonus Balance. Bonus is spent first on tickets; game winnings go to Main Balance. Withdrawals use Main Balance only.

Mini App wallet workflow update
- Deposit and Withdraw are separate in-app pages. Deposit requests are stored in deposit_requests with reference and optional screenshot data for the Admin Panel.
- Withdrawal requests are stored in withdrawal_requests and reserve Main Balance transactionally. Rejection refunds Main Balance; approval notifies the player but does not send money automatically.
- Deposit approval credits Bonus Balance. Winnings continue to credit Main Balance.
- Configure TELEBIRR_ACCOUNT_NAME and TELEBIRR_ACCOUNT_NUMBER in Render; defaults currently match the previously supplied account and must be verified before accepting payments.
