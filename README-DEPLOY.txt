TELEGRAM BINGO — UPDATED BUILD

Implemented flows
- Mandatory Telegram channel join before registration; bot checks membership and asks the user to tap Verify after joining.
- Registration is completed only after the user shares their own Telegram contact.
- New users receive the registration bonus (default 10 ETB) in Bonus Balance.
- Referral links use /start=ref_<telegram_id>. When a new invitee joins the required channel and completes phone registration, the referrer receives 20 ETB in Bonus Balance exactly once.
- Bingo ticket charges use Bonus Balance first, then Main Balance.
- Round refunds restore the exact wallet portions that were charged.
- Game winnings are credited to Main Balance (withdrawable/real balance), not Bonus Balance.
- Deposit requests require an amount and receipt photo; admin approval credits Main Balance and sets has_deposited=true.
- Deposits are available immediately after registration; a user does NOT need a previous deposit to submit a deposit request. The deposit is credited only after admin approval.
- Withdrawals are blocked until the user has at least one approved deposit. A withdrawal request reserves the amount from Main Balance; admin rejection refunds it. Admin approval marks it approved, after the admin manually sends the payout externally.
- Account, referral, deposit, withdrawal, rules and support bot menu items are included.

Render configuration
Build command: npm install
Start command: npm start

Required environment variables:
BOT_TOKEN=<new token from @BotFather>
WEBAPP_URL=https://<your-render-service>.onrender.com
BOT_CHANNEL_ID=-1004418660495
BOT_CHANNEL_URL=https://t.me/test16746g
ADMIN_ID=<your Telegram numeric user ID>
REGISTRATION_BONUS_ETB=10
REFERRAL_BONUS_ETB=20
DEPOSIT_INSTRUCTIONS=<your verified deposit payment instructions>
SUPPORT_CONTACT=@your_support_username
FIREBASE_KEY_PATH=/etc/secrets/firebase_key.json

Firebase Secret File:
Mount the service-account JSON at /etc/secrets/firebase_key.json.
The bot must be an administrator in the required channel so Telegram getChatMember can verify members reliably.
ADMIN_ID must be the Telegram account that will review deposit and withdrawal requests.

Important operational notes
- A deposit is not credited automatically: an admin must verify the receipt and approve the request.
- An approved withdrawal is a confirmation step; the admin must send the money through the configured external payment method.
- The project does not invent a bank/payment account. Set DEPOSIT_INSTRUCTIONS to the real payment details before enabling deposits.
- Do not commit BOT_TOKEN or firebase_key.json to GitHub. The previously exposed bot token must be revoked and replaced through @BotFather.
- Users must open the WebApp from the bot. Telegram initData is verified server-side, and API requests also check required channel membership when BOT_CHANNEL_ID is configured.

Deploy and verify
1. Replace the project files in the GitHub repository connected to Render.
2. Confirm all environment variables and the Firebase Secret File above.
3. Deploy with npm install / npm start.
4. Check https://<your-render-service>.onrender.com/health returns {"status":"ok"}.
5. Ensure the bot is an administrator in channel -1004418660495 (@test16746g). Test with a fresh Telegram account: join https://t.me/test16746g -> verify -> share own contact -> receive 10 ETB registration bonus.
6. Test a referral with a second fresh account: complete registration through the inviter link; inviter should receive 20 ETB bonus once.
7. Test deposit request and admin approval; verify Main Balance and has_deposited.
8. Test a withdrawal before deposit (must be blocked), then after approved deposit (must create admin review request).
9. Test a round using bonus funds; confirm winnings appear in Main Balance.

Validation
- Node syntax checks passed for server.js, bot.js, users.js and gameroom.js.
- Live Render, Telegram and Firebase end-to-end checks still need to be performed after deployment.
