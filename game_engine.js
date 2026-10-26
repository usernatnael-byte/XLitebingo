// ==========================================
// 🔥 FIREBASE CONFIGURATION & INITIALIZATION
// ==========================================
const firebaseConfig = {
    databaseURL: "https://ethio-bingo-app-default-rtdb.firebaseio.com/" // የራብዎን የ Firebase URL እዚህ ያስገቡ
};

// firebase ተጀምሮ መሆኑን በማረጋገጥ ላይ
if (!firebase.apps.length) {
    firebase.initializeApp(firebaseConfig);
}

const db = firebase.database();

// ==========================================
// 🎮 GAME ENGINE LOGIC WITH FIREBASE SYNC
// ==========================================

let selectedCards = [];
let currentUserId = Telegram.WebApp.initDataUnsafe?.user?.id || "test_user_123"; // ከቴሌግራም ዌብአፕ ዩዘር ID መቀበል

// ካርድ ሲመረጥ ወይም ሲሰረዝ ወደ Firebase ማዘመን
function toggleCard(cardId) {
    const cardElement = document.getElementById(`card-${cardId}`);
    if (!cardElement) return;

    if (selectedCards.includes(cardId)) {
        selectedCards = selectedCards.filter(id => id !== cardId);
        cardElement.classList.remove('selected');
    } else {
        if (selectedCards.length >= 4) {
            alert("⚠️ በአንድ ጊዜ መምረጥ የሚችሉት ከፍተኛው የካርድ ብዛት 4 ነው!");
            return;
        }
        selectedCards.push(cardId);
        cardElement.classList.add('selected');
    }

    // የተመረጡትን ካርዶች ወደ Firebase Realtime Database መቅዳት/ማስቀመጥ
    db.ref(`users/${currentUserId}/selected_cards`).set(selectedCards)
        .then(() => {
            console.log("✅ ካርዶች በ ዳታቤዝ ተመዝግበዋል:", selectedCards);
        })
        .catch((error) => {
            console.error("❌ ዳታቤዝ ላይ ማስቀመጥ አልተቻለም:", error);
        });

    updateStartButtonState();
}

function updateStartButtonState() {
    const startBtn = document.getElementById('start-game-btn');
    if (startBtn) {
        startBtn.disabled = selectedCards.length === 0;
    }
}

// ቆጠራ ጀምሮ ወደ Live Room ማሸጋገር
function startCountdownAndJoin() {
    if (selectedCards.length === 0) {
        alert("⚠️ እባክዎ ከመጀመርዎ በፊት ቢያንስ አንድ ካርድ ይምረጡ!");
        return;
    }

    document.getElementById('card-selection-screen').style.display = 'none';
    document.getElementById('countdown-screen').style.display = 'block';

    let countdown = 5;
    const timerDisplay = document.getElementById('countdown-timer');

    let countdownInterval = setInterval(() => {
        if (countdown > 0) {
            if (timerDisplay) timerDisplay.innerText = countdown;
            countdown--;
        } else {
            clearInterval(countdownInterval);
            enterLiveDrawingRoom();
        }
    }, 1000);
}

function enterLiveDrawingRoom() {
    document.getElementById('countdown-screen').style.display = 'none';
    document.getElementById('live-room-screen').style.display = 'block';

    // ከ Firebase ላይ የወጡ ቁጥሮችን (Drawn Numbers) ማዳመጥ (Realtime Listener)
    listenToLiveDraws();
}

// ከ Firebase የሚወጡ ቁጥሮችን በ Realtime መቀበል
function listenToLiveDraws() {
    const numberDisplay = document.getElementById('current-drawn-number');
    const historyContainer = document.getElementById('drawn-history');

    // የጨዋታውን ሩም ዳታቤዝ መከታተል
    db.ref("active_game/drawn_numbers").on("value", (snapshot) => {
        const numbers = snapshot.val() || [];
        if (numbers.length > 0) {
            const latestNum = numbers[numbers.length - 1]; // የቅርብ ጊዜ የወጣው ቁጥር
            
            if (numberDisplay) {
                numberDisplay.innerText = latestNum;
            }

            if (historyContainer) {
                // ታሪኩን በሙሉ ማሳየት
                historyContainer.innerHTML = "";
                numbers.forEach(num => {
                    const badge = document.createElement('span');
                    badge.className = 'drawn-badge';
                    badge.innerText = num;
                    historyContainer.appendChild(badge);
                });
            }
        }
    });
}
