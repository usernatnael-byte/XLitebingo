import math

TICKET_PRICE = 10
PRIZE_PER_CARTEL = 8
MAX_SELECTION = 4
CARTEL_COUNT = 500
BALLS = 75

_matrix_cache = {}

def _seeded_random(seed):
    x = math.sin(seed) * 10000
    return x - math.floor(x)

def generate_matrix(ticket_id):
    if ticket_id in _matrix_cache:
        return _matrix_cache[ticket_id]
    
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

def check_bingo(matrix, drawn_set):
    for r in range(5):
        if all(matrix[c][r] in drawn_set for c in range(5) if not (r == 2 and c == 2)):
            return True
    for c in range(5):
        if all(matrix[c][r] in drawn_set for r in range(5) if not (r == 2 and c == 2)):
            return True
    if all(matrix[i][i] in drawn_set for i in range(5) if i != 2):
        return True
    if all(matrix[4 - i][i] in drawn_set for i in range(5) if i != 2):
        return True
    return all(n in drawn_set for n in (matrix[0][0], matrix[4][0], matrix[0][4], matrix[4][4]))

def _mask_phone(phone):
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    return ("***" + digits[-4:]) if len(digits) >= 4 else ""
    
