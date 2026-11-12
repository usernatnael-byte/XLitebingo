const TICKET_PRICE = 10;
const PRIZE_PER_CARTEL = 8;
const MAX_SELECTION = 4;
const CARTEL_COUNT = 500;
const BALLS = 75;

const matrixCache = {};

const ETHIOPIAN_NAMES = [
    "አበበ ከበደ", "Meseret Haile", "ዳዊት መኮንን 🌟", "Tigist Assefa", "ዮናስ ታደሰ",
"Selam Abebe", "ከማል መሀመድ", "Helen Yosef", "ናትናኤል ሰለሞን", "Bethelhem Ayalew 👑",
"ቃልኪዳን ተስፋዬ", "Fikru Ayalew", "መቅደስ ታደሰ", "Samuel Girma", "ኤልሳቤጥ መብራቱ",
"Mikiyas Tekle", "ሀይማኖት ዘውዴ", "Endale Admasu", "ብርሀኑ ደቻሳ", "Anwar Yusuf 🌙",
"አማረ አያሌው", "Eyob Kebede", "አድነው መኮንን", "Belachew Assefa", "ጌታቸው ታደሰ",
"Melaku Abebe", "ስንታየሁ መሀመድ", "Tadesse Yosef", "ተፈሪ ሰለሞን", "Zenebech Ayalew",
"አለማየሁ ተስፋዬ 🌍", "Beyene Ayalew", "ደሳለኝ ታደሰ", "Eshetu Girma", "ፋንታሁን መብራቱ",
"Gizaw Tekle", "ሀብታሙ ዘውዴ", "Kebede Admasu", "ሊንሳ ደቻሳ", "Mohammed Yusuf",
"አሰፋ ከበደ", "Tamirat Haile", "ወርቁ መኮንን", "Yeshihareg Assefa", "ዘውዴ ታደሰ",
"Abraham Abebe", "ቢኒያም መሀመድ", "Dagmawi Yosef", "እሌኒ ሰለሞን", "Firon Ayalew",
"ገረመው ተስፋዬ", "Hanna Ayalew 🌻", "ኢዮርዳኖስ ታደሰ", "Kokeb Girma", "ሉላ መብራቱ",
"Meron Tekle", "ናኦት ዘውዴ", "Oliyad Admasu", "ጴጥሮስ ደቻሳ", "Qumneger Yusuf",
"ርብቃ ከበደ", "Sendek Haile", "ተመስገን መኮንን", "Wubshet Assefa", "ያዕቆብ ታደሰ",
"Azeb Abebe", "ብርቱካን መሀመድ", "Daniel Yosef", "ኤፍሬም ሰለሞን 🎸", "Fasika Ayalew",
"ገነት ተስፋዬ", "Hermela Ayalew", "ዮዲት ታደሰ", "Kiros Girma", "ሊዲያ መብራቱ",
"Marta Tekle", "ናርዶስ ዘውዴ", "Ornia Admasu", "ፓውሎስ ደቻሳ", "Rahel Yusuf",
"ሳራ ከበደ", "Tigist Haile", "ውይንቱ መኮንን", "Yared Assefa", "ዘሪቱ ታደሰ",
"Aklilu Abebe", "ቤተልሄም መሀመድ", "Dawit Yosef ✨", "እዮብ ሰለሞን", "Frehiwot Ayalew",
"ገረመው ካሳ", "Haymanot Ayalew", "ዮሐንስ ታደሰ", "Kasahun Girma", "ሊቀመናን መብራቱ",
"Mesay Tekle", "ናቲ ዘውዴ", "Endale Kassa", "ጳውሎስ ደቻሳ", "Qonjit Yusuf",
"ሩሃማ ከበደ", "Sendek Tadesse", "ተስፋዬ መኮንን", "Walelign Assefa", "ዮናታን ታደሰ",
"Abiy Abebe", "ባንቺአለም መሀመድ", "Dereje Yosef", "ኤልያስ ሰለሞን", "Fiker Ayalew ❤️",
"ገዛኸኝ ተስፋዬ", "Habtamu Ayalew", "ይበቃል ታደሰ", "Kebede Girma", "ልጅአለም መብራቱ",
"Mekonnen Tekle", "ናሁሰናይ ዘውዴ", "Oliyad Kassa", "ጴጥሮስ ታደሰ", "Qonjitu Yusuf",
"ርብቃ አበበ", "Solomon Haile", "ተፈራ መኮንን", "Worke Assefa", "ያዕቆብ ካሳ",
"Amarech Abebe", "ብርቄ መሀመድ", "Dagmawi Tadesse", "ኤፍሬም ታደሰ", "Fenta Ayalew",
"ገነት ካሳ", "Helen Ayalew", "ዮዲት ካሳ", "Kiros Tadesse", "ሊዲያ ታደሰ",
"Marta Abebe", "ናርዶስ ካሳ 💎", "Ornia Tadesse", "ፓውሎስ ታደሰ", "Rahel Abebe",
"ሳራ ካሳ", "Tigist Tadesse", "ውይንቱ ካሳ", "Yared Tadesse", "ዘሪቱ ካሳ",
"Aklilu Tadesse", "ቤተልሄም ካሳ", "Dawit Tadesse", "እዮብ ካሳ", "Frehiwot Tadesse",
"ዮሐንስ መላኩ", "Yordanos Zelalem", "ፍቃዱ አንዋር 🔥", "Teklehaimanot Tesfaye", "መሀመድ ቦጋለ",
"Jamal Ayele", "ጀማል ፍቅሩ", "Yonas Zelalem", "ሮቤል አርአያ", "Dejene Takele",
"አንበሴ ካሳ", "Yohannes Tadesse", "ዮርዳኖስ ኤልሳቤጥ", "Amare Mikias", "ግርማ ገብሩ",
"Lubaba Dechasa", "ይበቃል እንዳለ", "Lucas Helen", "ዑመር መቅደስ", "Worku Tadesse",
"ፍሬህይወት መሀመድ", "Sultan Samuel", "ግርማ ቤተልሄም", "Meseret Bethelhem", "መሰረት አርአያ",
"Birhanu Meseret", "ጴጥሮስ ቦጋለ", "Bogale Ayalew", "ምግቡ አብርሀ", "Abrha Muluken",
"ቢላል መቅደስ", "Ayele Zewde", "ናስር አያሌው", "Yonas Zewde", "ናትናኤል ግርማ",
"Estifanos Melaku", "አድማሱ አበበ", "Amina Mohammed", "ማርያም አብርሀ", "Haymanot Kemal",
"ዮናስ ታከለ", "Abrha Haymanot", "ዘላለም ሳሙኤል", "Fikadu Mikias", "ሀሰን ፍቃዱ",
"Belachew Admassu", "አህመድ መቅደስ", "Worku Mekdes", "ሙስጠፋ ሙሉቀን", "Mokonnen Samuel",
"ከበደ በቀለ", "Samuel Haymanot", "ተስፋዬ መሰረት", "Mekonnen Abrha", "ዮርዳኖስ ትግስት",
"Dejene Abrha", "አለማየሁ ቤተልሄም", "Mebratu Melaku", "መሀሪ መሀመድ", "Tesfaye Takele",
"አበባ መብራቱ", "Belachew Mohammed", "እምሩ ቤተልሄም", "Birtukan Alemayehu", "አስቴር አለማየሁ",
"Tsehay Gebru", "ገብሩ ሀይሉ", "Endale Zewde", "ሰለሞን አበበ", "Abebe Solomon",
"ግርማ ታደሰ", "Tadesse Mohammed", "ራሄል ሔለን", "Estifanos Dawit", "አድማሱ ደሳለኝ",
"Dechasa Anwar", "ሉባባ ደሳለኝ", "Girma Anwar", "ሉባባ ፍቅሩ", "Mekdes Anwar",
"ተስፋዬ ጌታቸው", "Mehari Dessalegn", "አሚና ሚኪያስ", "Yosef Kemal", "ገነት አብርሀ",
"Mesay Tadesse", "ሚኪያስ ሙሉቀን", "Worku Yusuf", "መላኩ በቀለ", "Kassa Mebratu",
"አያሌው አርአያ", "Abebe Yusuf", "ምህረት ዘላለም", "Woldesenbet Mekdes", "ማርያም ታከለ",
"Yohannes Zewde", "ኢብራሂም ሚኪያስ", "Sultan Mohammed", "ከበደ ኤልሳቤጥ", "Gebru Anwar",
"አለማየሁ ሀይሌ", "Ayele Melaku", "መሳይ ከበደ", "Bilal Birhanu", "መሰረት ቃልኪዳን",
"Yordanos Tigist", "አብርሀ መብራቱ", "Lucas Bekele", "አህመድ ብርሀኑ", "Dejene Assefa",
"ተመስገን አበበ", "Gebru Kebede", "በእነሱ ተስፋዬ", "Paulos Selam", "መላኩ ሀይሌ",
"Belachew Yosef", "ይስሀቅ ገብሩ", "Tsehay Dessalegn", "ሙስጠፋ ከበደ", "Mesay Yosef",
"ቢላል ታደሰ", "Temesgen Kalkidan", "ገነት ታደሰ", "Tsehay Tadesse", "ካሳ አያሌው",
"Birtukan Mekdes", "አስቴር ጌታቸው", "Girma Kemal", "አማረ ወርቁ", "Fikadu Yosef",
"ብርቱካን ገብሩ", "Temesgen Mekdes", "ካሳ አበበ", "Estifanos Tadesse", "ፀሀይ ሔለን",
"Fatima Mekdes", "ፍሬህይወት ዘላለም", "Yisak Mebratu", "በእነሱ ፍቅሩ", "Haymanot Muluken",
"ሐና ዮናስ", "Dejene Kassa", "ወርቁ ተክሌ", "Estifanos Kalkidan", "ፍቅሩ ሰላም",
"Fikadu Tesfaye", "ተክሌ አያሌው", "Worku Muluken", "አሊ መኮነን", "Mekonnen Natnael",
"ቢላ እንዳለ", "Mesay Mekdes", "ሰንደቅ ዮሴፍ", "Fikadu Selam", "አስቴር አየለ",
"Worku Dechasa", "ካሳ ገሰሰ", "Birhanu Tigist", "አህመድ አሰፋ", "Tigist Abebe",
"ፀሀይ አሰፋ", "Fatima Melaku", "ይስሀቅ መላኩ", "Amare Kemal", "ግንባሩ ተስፋዬ",
"Estifanos Meseret", "ከበደ ታደሰ", "Ayalew Bethelhem", "ሙሉቀን ካሳ", "Teklehaimanot Getachew",
"ተክሌ አሰፋ", "Estifanos Yonas", "በቀለ ሙሉቀን", "Woldesenbet Zelalem", "ሮቤል ዘውዴ",
"Teklehaimanot Haymanot", "መሀመድ ዘውዴ", "Markos Zewde", "እምሩ ታከለ", "Sultan Meseret",
"አብረሃም በላቸው", "Gebru Fikadu", "አንበሴ ሳሙኤል", "Birhanu Tadesse", "አያሌው ጌታቸው",
"Tesfaye Dawit", "ናትናኤል ታደሰ", "Dechasa Tekle", "አበበ መብራቱ", "Lubaba Mekdes",
"ኤልሳቤጥ ጌታቸው", "Yohannes Fikadu", "ጀማል ዮሴፍ", "Dejene Abebe", "ደቻሳ ሔለን",
"Abdul Fikru", "መሀመድ አድማሱ", "Nasir Tesfaye", "ኤልሳቤጥ ሳሙኤል", "Abrha Bethelhem",
"ከማል ተስፋዬ", "Dessalegn Gebru", "አሊ ሀይማኖት", "Maryam Abrha", "ተመስገን መኮንን",
"Birhanu Melaku", "ይበቃል አሰፋ", "Worku Birhanu", "ይስሀቅ ታደሰ", "Yosef Admassu",
"ፀሀይ ታደሰ", "Dejene Anwar", "ጌታቸው ካሳ", "Birhanu Mebratu", "ኤልሳቤጥ ካሳ",
"Kemal Mekonnen", "ብርሀኑ አየለ", "Zewde Mebratu", "ቢላ አብርሀ", "Kadija Solomon",
"ታደሰ ከማል", "Sultan Takele", "አበባ መኮንን", "Tigist Kebede", "ገብረማርያም ኤልሳቤጥ",
"Mekdes Haymanot", "ቤተልሄም ዮናስ", "Naol Muluken", "ይበቃል ሳሙኤል", "Mebratu Alemayehu",
"አለማየሁ ሰለሞን", "Estifanos Haymanot", "አዳነች ናትናኤል", "Natnael Takele", "እምሩ ሚኪያስ",
"Tigist Alemayehu", "ዩሱፍ አበበ", "Abdul Haymanot", "ታደሰ አበበ", "Zewde Assefa",
"ምህረት ከማል", "Zelalem Endale", "ካሳ ሔለን", "Hermela Takele", "አለማየሁ ዮሴፍ",
"Haile Dechasa", "ግርማ ዮሴፍ", "Mehari Girma", "ታከለ ጌታቸው", "Gebru Ayalew",
"ፋጡማ ሀይማኖት", "Emebet Bekele", "አብርሀ ሀይሉ", "Endale Kalkidan", "መሀመድ መሰረት",
"Markos Anwar", "ሙስጠፋ አያሌው", "Araya Samuel", "ምስራቅ ሰላም", "Birtukan Tadesse",
"ደሳለኝ ካሳ", "Zelalem Ayele", "ከዲጃ ትግስት", "Lubaba Haile", "ኢብራሂም ታከለ",
"Zelalem Bethelhem", "አሰፋው አያሌው", "Kassa Solomon", "ወርቁ አየለ", "Endale Kassa",
"ግርማ ደጀኔ", "Teklehaimanot Samuel", "ተስፋዬ ኤልሳቤጥ", "Anwar Abebe", "ተክለሀይማኖት እንዳለ",
"Selam Admassu", "ሉባባ ሙሉቀን", "Yusuf Mohammed", "ሐና መላኩ", "Aster Tekle",
"ይበቃል ትግስት", "Mokonnen Takele", "ግንባሩ አለማየሁ", "Yordanos Muluken", "ሰላም ቃልኪዳን",
"Petros Selam", "ዩሱፍ ካሳ", "Petros Abrha", "ብርቱካን ዘላለም", "Bekele Getachew",
"ዮሴፍ ሙሉቀን", "Maryam Muluken", "ቢተው ከማል", "Kadija Dechasa", "ሉባባ ተስፋዬ",
"Woldesenbet Natnael", "ከበደ ካሳ", "Teklehaimanot Fikadu", "ዩሱፍ መላኩ", "Worku Melaku",
"ዘውዴ መኮንን", "Sultan Solomon", "ራሄል አለማየሁ", "Lucas Gebru", "መቅደስ አበበ",
"Tigist Ayalew", "አስቴር መብራቱ", "Fatima Gebru", "ሉባባ ቤተልሄም", "Mehari Bethelhem",
"ይስሀቅ ወርቁ", "Kebede Tekle", "ሰለሞን ካሳ", "Aster Assefa", "አብዱል ሔለን",
"Lubaba Mikias", "አሚና ናትናኤል", "Bekele Haymanot", "ሮቤል መላኩ", "Paulos Bethelhem",
"ቢተው ቃልኪዳን", "Kassa Kemal", "ይበቃል ቦጋለ", "Maryam Gebru", "ከማል ብርሀኑ",
"Araya Zelalem", "ተክሌ እንዳለ", "Sultan Yusuf", "እድለም ከበደ", "Mekdes Tigist",
"ተክሌ ካሳ", "Naol Getachew", "ጌታቸው አበበ", "Emebet Amare", "ደሳለኝ መሀመድ",
"Bethelhem Fikadu", "ፋጡማ ካሳ", "Petros Natnael", "ብርሀኑ ወርቁ", "Tesfaye Endale",
"ናስር አሰፋ", "Anwar Selam", "ታከለ ግርማ", "Dejene Admassu", "ወልደሰንበት ከበደ",
"Bekele Zewde", "ይስሀቅ ሀይሌ", "Solomon Mikias", "ይበቃል ታደሰ", "Yohannes Muluken",
"ካሳ ግርማ", "Yordanos Tekle", "ቃልኪዳን መኮንን", "Tigist Endale", "ጳውሎስ ቃልኪዳን",
"Endale Bekele", "ሰለሞን መሰረት", "Woldesenbet Kalkidan", "አበባ በቀለ", "Selam Ayalew",
"አብዱ ዮሴፍ", "Abraham Ayalew", "ትግስት ፍቅሩ", "Gebremariam Tekle", "መቅደስ እንዳለ",
"Fikru Haile", "አያሌው ካሳ", "Fikadu Alemayehu", "በቀለ መቅደስ", "Zeyneb Girma",
"ሐና ቃልኪዳን", "Markos Tadesse", "መሀሪ ተክሌ", "Ayele Kebede", "ግንባሩ መላኩ",
"Araya Fikadu", "ዑመር አየለ", "Bilal Selam", "መሀሪ ፍቃዱ", "Mebratu Bethelhem",
"ገብሩ ግርማ", "Zelalem Gebru", "ሄርሜላ አየለ", "Worku Alemayehu", "በእነሱ አሰፋ",
"Zelalem Zewde", "ታደሰ ገብሩ", "Hermela Helen", "ቢተው ዩሱፍ", "Jamal Melaku",
"ዮሐንስ መቅደስ", "Zelalem Ayele", "መኮንን ሀይሉ", "Zeyneb Abrha", "ተስፋዬ አማረ",
"Kebede Bethelhem", "ጴጥሮስ ሙሉቀን", "Temesgen Tekle", "አድማሱ ፍቃዱ", "Birtukan Selam",
"አብዱ ከበደ", "Bethelhem Admassu", "መሀመድ ካሳ", "Mehari Samuel", "ሰንደቅ ተስፋዬ"
];

function seededRandom(seed) {
    let x = Math.sin(seed) * 10000;
    return x - Math.floor(x);
}

function generateMatrix(ticketId) {
    if (matrixCache[ticketId]) return matrixCache[ticketId];

    let seed = ticketId * 1573;
    let matrix = [];

    for (let col = 0; col < 5; col++) {
        let numbers = [];
        let low = col * 15 + 1;

        while (numbers.length < 5) {
            let value = low + Math.floor(seededRandom(seed) * 15);
            seed++;

            if (!numbers.includes(value)) numbers.push(value);
        }

        matrix.push(numbers);
    }

    matrixCache[ticketId] = matrix;
    return matrix;
}

function checkBingo(m, drawnSet) {
    for (let r = 0; r < 5; r++) {
        if ([0,1,2,3,4].every(c => (r === 2 && c === 2) || drawnSet.has(m[c][r]))) {
            return true;
        }
    }

    for (let c = 0; c < 5; c++) {
        if ([0,1,2,3,4].every(r => (r === 2 && c === 2) || drawnSet.has(m[c][r]))) {
            return true;
        }
    }

    if ([0,1,2,3,4].every(i => i === 2 || drawnSet.has(m[i][i]))) {
        return true;
    }

    if ([0,1,2,3,4].every(i => i === 2 || drawnSet.has(m[4 - i][i]))) {
        return true;
    }

    if (
        drawnSet.has(m[0][0]) &&
        drawnSet.has(m[4][0]) &&
        drawnSet.has(m[0][4]) &&
        drawnSet.has(m[4][4])
    ) {
        return true;
    }

    return false;
}

class GameEngine {
    constructor(wallet, min_players = 2, selection_seconds = 30, draw_interval = 3.0, result_seconds = 10) {
        this.wallet = wallet;
        this.min_players = Math.max(1, min_players);
        this.selection_seconds = selection_seconds;
        this.draw_interval = draw_interval;
        this.result_seconds = result_seconds;
        this.first_draw_delay = 3.0;

        this._seq = 0;
        this._threadRunning = false;
        this.on_round_result = null;

        this.botSettings = {
            botCount: 50,
            botWinPercent: 20,
            botCardsPerUser: 2,
            restrictDepositedWin: true
        };

        this._newRound();
    }

    setBotSettings(settings) {
        if (settings) {
            this.botSettings = { ...this.botSettings, ...settings };
        }
    }

    start() {
        this._threadRunning = true;
        this._runLoop();

        console.log(`🎰 Game engine started (min players: ${this.min_players})`);
    }

    stop() {
        this._threadRunning = false;
    }

    async _runLoop() {
        while (this._threadRunning) {
            try {
                await this._tick();
            } catch (e) {
                console.error('Engine tick error:', e);
            }

            await new Promise(resolve => setTimeout(resolve, 200));
        }
    }

    _newRound() {
        let now = Date.now() / 1000;

        this.round_id = `r${Math.floor(now * 1000)}`;
        this.phase = 'selection';
        this.phase_ends_at = now + this.selection_seconds;
        this.cartels = {};
        this.botProfiles = {};
        this.restrictedUsers = new Set();
        this.draw_order = [];
        this.drawn = [];
        this.next_draw_at = null;
        this.winners = [];
        this.no_winner = false;
        this._pending = null;
        this._botsInjected = false;
        this.botQueue = [];
        this.botInjectIndex = 0;

        this._seq++;
    }

    async pick(uid, cartel) {
        uid = String(uid);

        if (typeof cartel !== 'number' || cartel < 1 || cartel > CARTEL_COUNT) {
            return [false, 'invalid'];
        }

        if (this.phase !== 'selection') return [false, 'phase'];

        if (this.cartels[cartel] === uid) return [true, 'ok'];
        if (this.cartels[cartel]) return [false, 'taken'];

        let myCount = Object.values(this.cartels).filter(u => u === uid).length;

        if (myCount >= MAX_SELECTION) return [false, 'full'];

        try {
            let balance = await this.wallet.get_balance(uid);

            if (balance < (myCount + 1) * TICKET_PRICE) {
                return [false, 'balance'];
            }
        } catch (e) {
            return [false, 'error'];
        }

        if (this.phase !== 'selection') return [false, 'phase'];

        this.cartels[cartel] = uid;
        this._seq++;

        return [true, 'ok'];
    }

    unpick(uid, cartel) {
        uid = String(uid);

        if (this.phase !== 'selection') return [false, 'phase'];

        if (this.cartels[cartel] === uid) {
            delete this.cartels[cartel];
            this._seq++;
        }

        return [true, 'ok'];
    }

    get_state(uid) {
        uid = String(uid);

        let mine = Object.keys(this.cartels)
            .filter(c => this.cartels[c] === uid)
            .map(Number);

        let winners = [];

        if (this.phase === 'result') {
            winners = this.winners.map(w => ({
                name: w.name || 'Player',
                cartel: w.cartel,
                prize: w.prize,
                mine: w.uid === uid
            }));
        }

        const uniquePlayers = new Set(Object.values(this.cartels));

        return {
            round_id: this.round_id,
            seq: this._seq,
            phase: this.phase,
            server_time: Date.now() / 1000,
            phase_ends_at: ['selection', 'result'].includes(this.phase) ? this.phase_ends_at : null,
            selection_seconds: this.selection_seconds,
            result_seconds: this.result_seconds,
            min_players: this.min_players,
            players: uniquePlayers.size,
            taken: Object.keys(this.cartels).map(Number),
            my_cartels: mine,
            pool: Object.keys(this.cartels).length * PRIZE_PER_CARTEL,
            drawn: this.drawn,
            winners: winners,
            no_winner: this.phase === 'result' ? this.no_winner : false
        };
    }

    async _tick() {
        let now = Date.now() / 1000;

        if (this.phase === 'selection') {
            if (!this._botsInjected) {
                this._initBotsQueue();
                this._botsInjected = true;
            }

            this._processBotQueue();

            if (now >= this.phase_ends_at) {
                let activePlayers = new Set(Object.values(this.cartels)).size;

                if (activePlayers < this.min_players) {
                    this.phase_ends_at = now + this.selection_seconds;
                    this._seq++;
                } else {
                    this.phase = 'locking';
                    this._seq++;

                    await this._do_lock(this.cartels);
                }
            }
        } else if (this.phase === 'drawing') {
            if (now >= this.next_draw_at) {
                this._draw_one(now);
            }

            if (this.phase === 'settling') {
                await this._do_settle();
            }
        } else if (this.phase === 'settling') {
            await this._do_settle();
        } else if (this.phase === 'result') {
            if (now >= this.phase_ends_at) {
                this._newRound();
            }
        }
    }

    _initBotsQueue() {
        const targetBotCount = Math.min(400, Math.max(0, this.botSettings.botCount || 0));
        const cardsPerBot = Math.min(4, Math.max(1, this.botSettings.botCardsPerUser || 2));
        this.botProfiles = {};
        this.botQueue = [];

        for (let i = 0; i < targetBotCount; i++) {
            const botId = `bot_${i + 1}`;
            const randomName = ETHIOPIAN_NAMES[Math.floor(Math.random() * ETHIOPIAN_NAMES.length)] + ` (${Math.floor(Math.random() * 900 + 100)})`;
            
            this.botProfiles[botId] = { name: randomName };

            const howManyCards = Math.floor(Math.random() * cardsPerBot) + 1;
            for (let c = 0; c < howManyCards; c++) {
                this.botQueue.push(botId);
            }
        }

        this.botQueue.sort(() => Math.random() - 0.5);
        this.botInjectIndex = 0;
    }

    _processBotQueue() {
        if (!this.botQueue || this.botInjectIndex >= this.botQueue.length) return;

        let steps = Math.floor(Math.random() * 3) + 1;
        let changed = false;

        for (let s = 0; s < steps && this.botInjectIndex < this.botQueue.length; s++) {
            const botId = this.botQueue[this.botInjectIndex++];
            
            let availableCartels = [];
            for (let i = 1; i <= CARTEL_COUNT; i++) {
                if (!this.cartels[i]) availableCartels.push(i);
            }

            if (availableCartels.length === 0) break;

            const chosenCartel = availableCartels[Math.floor(Math.random() * availableCartels.length)];
            
            const botExistingCount = Object.values(this.cartels).filter(u => u === botId).length;
            if (botExistingCount < MAX_SELECTION) {
                this.cartels[chosenCartel] = botId;
                changed = true;
            }
        }

        if (changed) {
            this._seq++;
        }
    }

    async _do_lock(snapshot) {
        let rid = this.round_id;

        await this.wallet.begin_round(rid, snapshot);

        let realSnapshot = {};
        for (let [cartel, uid] of Object.entries(snapshot)) {
            if (!String(uid).startsWith('bot_')) {
                realSnapshot[cartel] = uid;
            }
        }

        let byUser = {};

        for (let [cartel, uid] of Object.entries(realSnapshot)) {
            if (!byUser[uid]) byUser[uid] = [];
            byUser[uid].push(Number(cartel));
        }

        let paid = {};
        this.restrictedUsers = new Set();

        for (let [uid, cartels] of Object.entries(byUser)) {
            let res = await this.wallet.charge(
                uid,
                cartels.length * TICKET_PRICE,
                rid,
                cartels.length
            );

            if (res !== null) {
                for (let c of cartels) paid[c] = uid;

                if (this.botSettings.restrictDepositedWin) {
                    const prof = await this.wallet.profile(uid);
                    if (prof && prof.has_deposited) {
                        this.restrictedUsers.add(String(uid));
                    }
                }
            } else {
                await this.wallet.refund(uid, rid);
            }
        }

        for (let [cartel, uid] of Object.entries(snapshot)) {
            if (String(uid).startsWith('bot_')) {
                paid[cartel] = uid;
            }
        }

        this.cartels = paid;

        try {
            await this.wallet.start_drawing(rid, paid);
        } catch (error) {
            console.error('Could not persist drawing round; refunding tickets:', error);
            let realPaidUids = [...new Set(Object.values(paid).filter(u => !String(u).startsWith('bot_')))];
            await this.wallet.cancel_round(rid, realPaidUids);
            this.cartels = {};
            this.phase = 'selection';
            this.phase_ends_at = Date.now() / 1000 + this.selection_seconds;
            this._seq++;
            return;
        }

        let order = Array.from({ length: BALLS }, (_, i) => i + 1);

        for (let i = order.length - 1; i > 0; i--) {
            let j = Math.floor(Math.random() * (i + 1));
            [order[i], order[j]] = [order[j], order[i]];
        }

        this.draw_order = order;
        this.drawn = [];
        this.phase = 'drawing';
        this.next_draw_at = Date.now() / 1000 + this.first_draw_delay;

        this._seq++;
    }

    _draw_one(now) {
        let nextIndex = this.drawn.length;
        let chosenNumber = this.draw_order[nextIndex];

        if (this.botSettings.restrictDepositedWin && this.restrictedUsers && this.restrictedUsers.size > 0) {
            let safeIndex = -1;

            for (let i = nextIndex; i < this.draw_order.length; i++) {
                let candidateNum = this.draw_order[i];
                let testSet = new Set(this.drawn);
                testSet.add(candidateNum);

                let makesRestrictedWin = false;

                for (let [cartel, uid] of Object.entries(this.cartels)) {
                    if (this.restrictedUsers.has(String(uid))) {
                        if (checkBingo(generateMatrix(Number(cartel)), testSet)) {
                            makesRestrictedWin = true;
                            break;
                        }
                    }
                }

                if (!makesRestrictedWin) {
                    safeIndex = i;
                    break;
                }
            }

            if (safeIndex !== -1) {
                chosenNumber = this.draw_order[safeIndex];
                this.draw_order[safeIndex] = this.draw_order[nextIndex];
                this.draw_order[nextIndex] = chosenNumber;
            } else {
                const nonRestrictedCartels = Object.entries(this.cartels)
                    .filter(([c, u]) => !this.restrictedUsers.has(String(u)))
                    .map(([c]) => Number(c));

                if (nonRestrictedCartels.length > 0) {
                    const luckyCartel = nonRestrictedCartels[Math.floor(Math.random() * nonRestrictedCartels.length)];
                    this._pending = ['win', [luckyCartel]];
                    this.phase = 'settling';
                    return;
                }
            }
        }

        let number = chosenNumber;
        this.drawn.push(number);
        this._seq++;

        let drawnSet = new Set(this.drawn);
        let winning = [];

        for (let [cartel, uid] of Object.entries(this.cartels)) {
            if (checkBingo(generateMatrix(Number(cartel)), drawnSet)) {
                winning.push(Number(cartel));
            }
        }

        if (winning.length === 0 && this.drawn.length >= 25) {
            const botWinChance = Number(this.botSettings.botWinPercent) || 0;
            if (Math.random() * 100 < botWinChance) {
                const botCartels = Object.entries(this.cartels)
                    .filter(([c, u]) => String(u).startsWith('bot_'))
                    .map(([c]) => Number(c));
                
                if (botCartels.length > 0) {
                    const chosenBotCartel = botCartels[Math.floor(Math.random() * botCartels.length)];
                    winning.push(chosenBotCartel);
                }
            }
        }

        if (winning.length > 0) {
            this._pending = ['win', winning];
            this.phase = 'settling';
        } else if (this.drawn.length >= BALLS) {
            this._pending = ['none', []];
            this.phase = 'settling';
        } else {
            this.next_draw_at = Math.max(
                this.next_draw_at + this.draw_interval,
                now
            );
        }
    }

    async _do_settle() {
        let rid = this.round_id;
        let tickets = { ...this.cartels };
        let pending = this._pending;
        let pool = 0;

        if (pending[0] === 'win') {
            let wins = pending[1];

            pool = Object.keys(tickets).length * PRIZE_PER_CARTEL;

            let share = Math.round((pool / wins.length) * 100) / 100;
            let payouts = {};
            let realWinnersList = [];

            for (let c of wins) {
                let uid = tickets[c];
                if (!String(uid).startsWith('bot_')) {
                    payouts[uid] = (payouts[uid] || 0) + share;
                }
                realWinnersList.push({ cartel: c, uid: uid });
            }

            let profiles = {};

            for (let uid of Object.keys(payouts)) {
                profiles[uid] = await this.wallet.profile(uid) || {};
            }

            if (Object.keys(payouts).length > 0) {
                await this.wallet.prepare_settlement(rid, payouts);
                await this.wallet.settle(rid, payouts);
            }

            this.winners = realWinnersList.map(w => {
                const isBot = String(w.uid).startsWith('bot_');
                let winnerName = 'Player';
                if (isBot) {
                    winnerName = this.botProfiles[w.uid]?.name || 'ተጫዋች';
                } else {
                    winnerName = profiles[w.uid]?.name || profiles[w.uid]?.username || 'Player';
                }

                return {
                    uid: w.uid,
                    cartel: w.cartel,
                    prize: share,
                    name: winnerName
                };
            });

            this.no_winner = false;
        } else {
            let realUserIds = [...new Set(Object.entries(tickets).filter(([c, u]) => !String(u).startsWith('bot_')).map(([c, u]) => u))];
            await this.wallet.cancel_round(rid, realUserIds);

            this.winners = [];
            this.no_winner = true;
        }

        this.phase = 'result';
        this.phase_ends_at = Date.now() / 1000 + this.result_seconds;

        this._seq++;

        if (this.on_round_result) {
            let uniquePlayers = new Set(Object.values(tickets));

            this.on_round_result({
                round_id: rid,
                players: uniquePlayers.size,
                cartels: Object.keys(tickets).length,
                pool: pool,
                balls: this.drawn.length,
                no_winner: this.no_winner,
                winners: this.winners
            });
        }
    }
}

module.exports = {
    GameEngine,
    TICKET_PRICE,
    PRIZE_PER_CARTEL,
    MAX_SELECTION,
    generateMatrix
};
