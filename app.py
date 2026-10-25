<!DOCTYPE html>
<html lang="am">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Spark Bingo - Live, Cartela & Wallet</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: sans-serif; }
        body { background: #0b0f19; color: #fff; min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding-bottom: 60px; }
        
        /* Top Bar */
        .top-bar { width: 100%; max-width: 480px; padding: 8px 12px; background: #131b2e; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #2a3b5c; flex-shrink: 0; }
        .brand-title { font-size: 13px; font-weight: 800; color: #fff; }
        .user-badge { display: flex; align-items: center; gap: 6px; background: #172138; padding: 2px 8px; border-radius: 20px; border: 1px solid #2a3b5c; font-size: 11px; }
        .user-avatar { width: 20px; height: 20px; background: #f39c12; color: #000; font-weight: bold; border-radius: 50%; display: flex; align-items: center; justify-content: center; }

        /* Stats & Countdown / AutoPlay Panel */
        .stats-box { width: 100%; max-width: 480px; padding: 8px 12px; background: #131b2e; display: flex; flex-direction: column; gap: 6px; border-bottom: 1px solid #2a3b5c; flex-shrink: 0; }
        .bal-row { display: flex; justify-content: space-between; font-size: 11px; font-weight: bold; }
        .bal-val { color: #f39c12; }
        
        .info-row { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
        .info-card { background: #172138; border: 1px solid #2a3b5c; border-radius: 6px; padding: 6px; text-align: center; }
        .info-label { font-size: 9px; color: #8c9cb6; margin-bottom: 1px; }
        .info-value { font-size: 13px; font-weight: bold; color: #ffcc00; }

        .container { width: 100%; max-width: 480px; padding: 8px 10px; display: none; flex-direction: column; gap: 8px; }
        .container.active { display: flex; }

        /* Cartela Picker Grid (1 - 400) */
        .selection-header { display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-weight: bold; margin-bottom: 6px; color: #f39c12; }
        .cartela-picker-grid { display: grid; grid-template-columns: repeat(10, 1fr); gap: 4px; background: #172138; padding: 8px; border-radius: 10px; border: 1px solid #2a3b5c; max-height: 350px; overflow-y: auto; }
        .picker-cell { background: #0b0f19; aspect-ratio: 1; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: bold; color: #8c9cb6; border-radius: 3px; cursor: pointer; border: 1px solid #2a3b5c; }
        .picker-cell.selected { background: #f39c12; color: #000; border-color: #fff; box-shadow: 0 0 6px #f39c12; }

        /* Live Room Styles */
        .live-top-panel { background: #131b2e; border: 1px solid #2a3b5c; border-radius: 8px; padding: 8px 10px; display: flex; flex-direction: column; gap: 6px; flex-shrink: 0; }
        .live-header-row { display: flex; justify-content: space-between; align-items: center; }
        
        .main-ball-box { width: 44px; height: 44px; border-radius: 50%; background: linear-gradient(135deg, #f39c12, #d35400); display: flex; flex-direction: column; align-items: center; justify-content: center; font-size: 11px; font-weight: bold; color: #fff; border: 2px solid #ffcc00; box-shadow: 0 0 6px rgba(243,156,12,0.4); text-align: center; line-height: 1.1; }

        /* Called Numbers History Bar */
        .called-history-container { display: flex; align-items: center; gap: 4px; overflow-x: auto; padding-bottom: 4px; white-space: nowrap; scrollbar-width: thin; }
        .called-history-container::-webkit-scrollbar { height: 4px; }
        .called-history-container::-webkit-scrollbar-thumb { background: #2a3b5c; border-radius: 2px; }
        
        .history-ball { min-width: 32px; height: 22px; border-radius: 11px; background: #172138; border: 1px solid #2a3b5c; display: inline-flex; align-items: center; justify-content: center; font-size: 9px; font-weight: bold; color: #8c9cb6; padding: 0 4px; }
        .history-ball.latest { background: #f39c12; color: #000; border-color: #fff; box-shadow: 0 0 4px #f39c12; }

        /* Auto Play Toggle Bar */
        .autoplay-bar { background: #172138; border: 1px solid #2a3b5c; border-radius: 6px; padding: 8px 10px; display: flex; justify-content: space-between; align-items: center; font-size: 11px; font-weight: bold; flex-shrink: 0; }
        .switch { position: relative; display: inline-block; width: 36px; height: 20px; }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #2a3b5c; transition: .4s; border-radius: 20px; }
        .slider:before { position: absolute; content: ""; height: 14px; width: 14px; left: 3px; bottom: 3px; background-color: white; transition: .4s; border-radius: 50%; }
        input:checked + .slider { background-color: #f39c12; }
        input:checked + .slider:before { transform: translateX(16px); }

        /* 2x2 Grid for Cartelas */
        .cartelas-container { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        .cartela-card { background: #172138; border: 1px solid #2a3b5c; border-radius: 8px; padding: 6px; box-shadow: 0 2px 6px rgba(0,0,0,0.3); display: flex; flex-direction: column; justify-content: space-between; }
        .cartela-header { text-align: center; font-size: 10px; font-weight: bold; color: #f39c12; border-bottom: 1px solid #2a3b5c; padding-bottom: 3px; margin-bottom: 4px; }
        
        .bingo-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 2px; background: #2a3b5c; padding: 2px; border-radius: 4px; }
        .cell { background: #0b0f19; aspect-ratio: 1.15; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: bold; border-radius: 2px; color: #fff; cursor: pointer; }
        .cell.head { background: #131b2e; color: #f39c12; font-size: 10px; cursor: default; }
        .cell.marked { background: #f39c12; color: #000; box-shadow: 0 0 3px #f39c12; }
        .cell.manual-marked { background: #27ae60; color: #fff; box-shadow: 0 0 3px #27ae60; }

        .manual-bingo-btn { width: 100%; padding: 4px; background: #2a3b5c; color: #8c9cb6; border: none; border-radius: 4px; font-size: 9px; font-weight: bold; cursor: not-allowed; transition: 0.3s; margin-top: 4px; }
        .manual-bingo-btn.ready { background: #f39c12; color: #000; cursor: pointer; box-shadow: 0 0 4px #f39c12; }
        .manual-bingo-btn.hidden { display: none; }

        /* Modal Popups */
        .modal-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); display: none; align-items: center; justify-content: center; z-index: 2000; }
        .modal-content { background: #131b2e; border: 2px solid #f39c12; border-radius: 16px; padding: 25px; width: 90%; max-width: 320px; text-align: center; box-shadow: 0 0 20px rgba(243,156,12,0.5); }
        .modal-title { font-size: 22px; font-weight: bold; color: #ffcc00; margin-bottom: 10px; }
        .modal-text { font-size: 14px; color: #fff; margin-bottom: 15px; line-height: 1.5; }
        .modal-timer { font-size: 13px; color: #8c9cb6; margin-top: 10px; }

        /* Footer Navigation */
        .footer { position: fixed; bottom: 0; left: 50%; transform: translateX(-50%); width: 100%; max-width: 480px; background: #0d1322; display: flex; justify-content: space-around; padding: 8px 0; border-top: 1px solid #2a3b5c; z-index: 1000; }
        .nav-link { color: #8c9cb6; font-size: 10px; cursor: pointer; text-align: center; flex: 1; }
        .nav-link.active { color: #ffcc00; }
        .nav-link span { font-size: 15px; display: block; }
    </style>
</head>
<body>

    <!-- Top Navigation Bar -->
    <header class="top-bar">
        <div class="brand-title">|Spark Bingo|</div>
        <div class="user-badge">
            <span>Nhatty</span>
            <div class="user-avatar">N</div>
        </div>
    </header>

    <!-- Stats & Countdown / AutoPlay Panel -->
    <div class="stats-box">
        <div class="bal-row">
            <span>PLAY BAL: <span class="bal-val" id="topPlayBal">555.00</span></span>
            <span>MAIN BAL: <span class="bal-val" id="topMainBal">0.60</span></span>
        </div>
        
        <!-- Home Page Countdown Row (Visible only on Home) -->
        <div class="info-row" id="homeCountdownRow">
            <div class="info-card">
                <div class="info-label">ጨዋታው ሊጀምር ነው</div>
                <div class="info-value" id="countdownTimer">00:30</div>
            </div>
            <div class="info-card">
                <div class="info-label">ድል አድራጊ ሽልማት</div>
                <div class="info-value">2,007.50 ETB</div>
            </div>
        </div>

        <!-- Live Room Auto Play Mode Bar -->
        <div class="autoplay-bar" id="liveAutoPlayBar" style="display: none;">
            <span>Auto Play Mode (አውቶማቲክ ምልክት)</span>
            <label class="switch">
                <input type="checkbox" id="autoPlayToggle" checked onchange="handleAutoPlayToggleChange()">
                <span class="slider"></span>
            </label>
        </div>
    </div>

    <!-- 1. HOME / CARTELA SELECTION PAGE -->
    <div id="homePage" class="container active">
        <div class="card" style="background: #172138; border: 1px solid #2a3b5c; border-radius: 12px; padding: 12px; text-align: left;">
            <div class="selection-header">
                <span>ካርቴላ ይምረጡ (ከ 1 እስከ 400)</span>
                <span id="selectedCount">መረጡ: 0 / 4</span>
            </div>
            <p style="font-size: 11px; color: #8c9cb6; margin-bottom: 8px;">ከ 1 እስከ 4 ካርቴላዎች መምረጥ ይችላሉ። (ሰዓቱ ሲያልቅ በራሱ ወደ Live Room ይገባል)</p>
            
            <div class="cartela-picker-grid" id="pickerGrid"></div>
        </div>
    </div>

    <!-- 2. WALLET PAGE -->
    <div id="walletPage" class="container">
        <div style="background: #172138; border: 1px solid #2a3b5c; border-radius: 12px; padding: 12px; display: flex; flex-direction: column; gap: 10px;">
            <div style="font-size: 13px; font-weight: bold; color: #f39c12; text-align: center; margin-bottom: 2px;">💳 የኪስ ቦርሳ (Wallet)</div>
            
            <!-- Balances Box -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                <div style="background: #0b0f19; padding: 8px; border-radius: 8px; text-align: center; border: 1px solid #2a3b5c;">
                    <div style="font-size: 9px; color: #8c9cb6;">PLAY BALANCE</div>
                    <div style="font-size: 13px; font-weight: bold; color: #f39c12;" id="walletPlayBal">555.00 ETB</div>
                </div>
                <div style="background: #0b0f19; padding: 8px; border-radius: 8px; text-align: center; border: 1px solid #2a3b5c;">
                    <div style="font-size: 9px; color: #8c9cb6;">MAIN BALANCE</div>
                    <div style="font-size: 13px; font-weight: bold; color: #27ae60;" id="walletMainBal">0.60 ETB</div>
                </div>
            </div>

            <!-- Deposit / Withdraw Mode Switch Buttons -->
            <div style="display: flex; gap: 6px; margin-top: 2px;">
                <button onclick="switchWalletTab('deposit')" id="depTabBtn" style="flex:1; padding:6px; background:#f39c12; color:#000; border:none; border-radius:6px; font-size:11px; font-weight:bold; cursor:pointer;">ዲፖዚት (Deposit)</button>
                <button onclick="switchWalletTab('withdraw')" id="withTabBtn" style="flex:1; padding:6px; background:#0b0f19; color:#8c9cb6; border:1px solid #2a3b5c; border-radius:6px; font-size:11px; font-weight:bold; cursor:pointer;">ዊዝድሮው (Withdraw)</button>
            </div>

            <!-- Deposit Section -->
            <div id="depositSection" style="display: flex; flex-direction: column; gap: 8px;">
                <div style="background: #0b0f19; padding: 8px; border-radius: 6px; border: 1px solid #2a3b5c; font-size: 10px; line-height: 1.4; color: #8c9cb6;">
                    ℹ️ <b>ዲፖዚት ለማድረግ:</b> ከ 100 ብር ጀምሮ ይቻላል።<br>
                    የቴሌብር አካውንት: <b style="color:#ffcc00;">0949196145</b> (Natnael Girma)<br>
                    ገንዘቡን ከላኩ በኋላ የክፍያ ማረጋገጫ (Transaction ID) ከታች አስገብተው ይላኩ።
                </div>
                <div>
                    <label style="font-size: 10px; color: #8c9cb6; display: block; margin-bottom: 2px;">የብር መጠን (ቢያንስ 100 ETB)</label>
                    <input type="number" id="depositAmount" placeholder="100" style="width: 100%; padding: 6px; background: #0b0f19; border: 1px solid #2a3b5c; border-radius: 4px; color: #fff; font-size: 11px;">
                </div>
                <div>
                    <label style="font-size: 10px; color: #8c9cb6; display: block; margin-bottom: 2px;">Transaction ID (የክፍያ ማረጋገጫ ቁጥር)</label>
                    <input type="text" id="depositTxId" placeholder="ለምሳሌ: FT23..." style="width: 100%; padding: 6px; background: #0b0f19; border: 1px solid #2a3b5c; border-radius: 4px; color: #fff; font-size: 11px;">
                </div>
                <button onclick="submitDeposit()" style="width: 100%; padding: 8px; background: #f39c12; color: #000; border: none; border-radius: 6px; font-size: 11px; font-weight: bold; cursor: pointer; margin-top: 2px;">ዲፖዚት ጥያቄ ወደ አድሚን ቦት ላክ</button>
            </div>

            <!-- Withdraw Section -->
            <div id="withdrawSection" style="display: none; flex-direction: column; gap: 8px;">
                <div style="background: #0b0f19; padding: 8px; border-radius: 6px; border: 1px solid #2a3b5c; font-size: 10px; line-height: 1.4; color: #8c9cb6;">
                    ℹ️ <b>ዊዝድሮው ለማድረግ:</b> ከ 300 ብር ጀምሮ ማውጣት ይቻላል። እባክዎ ትክክለኛ የባንክ ወይም የቴሌብር መረጃ ያስገቡ።
                </div>
                <div>
                    <label style="font-size: 10px; color: #8c9cb6; display: block; margin-bottom: 2px;">የብር መጠን (ቢያንስ 300 ETB)</label>
                    <input type="number" id="withdrawAmount" placeholder="300" style="width: 100%; padding: 6px; background: #0b0f19; border: 1px solid #2a3b5c; border-radius: 4px; color: #fff; font-size: 11px;">
                </div>
                <div>
                    <label style="font-size: 10px; color: #8c9cb6; display: block; margin-bottom: 2px;">የባንክ / የክፍያ ዓይነት</label>
                    <select id="withdrawBankType" style="width: 100%; padding: 6px; background: #0b0f19; border: 1px solid #2a3b5c; border-radius: 4px; color: #fff; font-size: 11px;">
                        <option value="Telebirr">Telebirr</option>
                        <option value="CBE">CBE (የኢትዮጵያ ንግድ ባንክ)</option>
                    </select>
                </div>
                <div>
                    <label style="font-size: 10px; color: #8c9cb6; display: block; margin-bottom: 2px;">የባንክ / የቴሌብር አካውንት ቁጥር እና ስም</label>
                    <input type="text" id="withdrawAccountInfo" placeholder="ቁጥር እና ሙሉ ስም ያስገቡ" style="width: 100%; padding: 6px; background: #0b0f19; border: 1px solid #2a3b5c; border-radius: 4px; color: #fff; font-size: 11px;">
                </div>
                <button onclick="submitWithdraw()" style="width: 100%; padding: 8px; background: #27ae60; color: #fff; border: none; border-radius: 6px; font-size: 11px; font-weight: bold; cursor: pointer; margin-top: 2px;">የብር ውጣ ጥያቄ (Withdraw) ላክ</button>
            </div>
        </div>
    </div>

    <!-- 3. PROFILE PAGE (Gambling Style Profile & Invite Link) -->
    <div id="profilePage" class="container">
        <div style="background: #172138; border: 1px solid #2a3b5c; border-radius: 12px; padding: 12px; display: flex; flex-direction: column; gap: 8px;">
            <!-- User Header info -->
            <div style="display: flex; align-items: center; gap: 10px; border-bottom: 1px solid #2a3b5c; padding-bottom: 8px;">
                <div style="width: 44px; height: 44px; background: #f39c12; color: #000; font-size: 18px; font-weight: bold; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">N</div>
                <div style="overflow: hidden;">
                    <div style="font-size: 13px; font-weight: bold; color: #fff;">Nhatty</div>
                    <div style="font-size: 10px; color: #8c9cb6;">ID: #894210 | አባልነት: <span style="color: #ffcc00;">VIP ተጫዋች</span></div>
                </div>
            </div>

            <!-- Gambling Stats Grid -->
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px;">
                <div style="background: #0b0f19; padding: 6px; border-radius: 6px; text-align: center; border: 1px solid #2a3b5c;">
                    <div style="font-size: 9px; color: #8c9cb6;">ጠቅላላ ጨዋታ</div>
                    <div style="font-size: 12px; font-weight: bold; color: #fff; margin-top: 2px;">48</div>
                </div>
                <div style="background: #0b0f19; padding: 6px; border-radius: 6px; text-align: center; border: 1px solid #2a3b5c;">
                    <div style="font-size: 9px; color: #8c9cb6;">ያሸነፈባቸው</div>
                    <div style="font-size: 12px; font-weight: bold; color: #27ae60; margin-top: 2px;">14</div>
                </div>
                <div style="background: #0b0f19; padding: 6px; border-radius: 6px; text-align: center; border: 1px solid #2a3b5c;">
                    <div style="font-size: 9px; color: #8c9cb6;">አጠቃላይ ትርፍ</div>
                    <div style="font-size: 12px; font-weight: bold; color: #f39c12; margin-top: 2px;">+3,450 Br</div>
                </div>
            </div>

            <!-- Extra Player Info -->
            <div style="background: #0b0f19; padding: 8px; border-radius: 6px; border: 1px solid #2a3b5c; font-size: 10px; display: flex; flex-direction: column; gap: 4px;">
                <div style="display: flex; justify-content: space-between;"><span>የተመዘገበበት ቦታ:</span> <b style="color: #fff;">ሆሳዕና, ኢትዮጵያ</b></div>
                <div style="display: flex; justify-content: space-between;"><span>የተሳካ ዊንሬት (Win Rate):</span> <b style="color: #27ae60;">29.1%</b></div>
                <div style="display: flex; justify-content: space-between;"><span>የመጨረሻ ጨዋታ:</span> <b style="color: #f39c12;">ዛሬ (Live Room)</b></div>
            </div>

            <!-- Invite / Referral Section -->
            <div style="background: #0b0f19; padding: 8px; border-radius: 6px; border: 1px solid #2a3b5c; display: flex; flex-direction: column; gap: 6px;">
                <div style="font-size: 11px; font-weight: bold; color: #ffcc00; display: flex; align-items: center; gap: 4px;">
                    <span>👥</span> ጓደኛን ጋብዝ (Invite & Earn)
                </div>
                <div style="font-size: 9px; color: #8c9cb6; line-height: 1.3;">
                    ሊንኩን ለጓደኛዎ በማጋራት ሲመዘገቡ ቦነስ ያግኙ!
                </div>
                <div style="display: flex; gap: 4px;">
                    <input type="text" id="inviteLinkInput" value="https://t.me/SparkBingoBot?start=ref_894210" readonly style="flex: 1; padding: 5px; background: #131b2e; border: 1px solid #2a3b5c; border-radius: 4px; color: #ffcc00; font-size: 10px;">
                    <button onclick="copyInviteLink()" style="padding: 5px 10px; background: #f39c12; color: #000; border: none; border-radius: 4px; font-size: 10px; font-weight: bold; cursor: pointer;">ቅዳ (Copy)</button>
                </div>
            </div>
        </div>
    </div>

    <!-- 4. LIVE BINGO ROOM PAGE -->
    <div id="livePage" class="container">
        <div class="live-top-panel">
            <div class="live-header-row">
                <div>
                    <div style="font-size: 9px; color: #8c9cb6;" id="roundLabel">Round: #1</div>
                    <div style="font-size: 11px; font-
