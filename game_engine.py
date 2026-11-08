import random, copy
from decimal import Decimal, ROUND_HALF_UP
CLUB_OPTIONS = {'1': ('Real Madrid', 300),
 '2': ('Barcelona', 250),
 '3': ('Arsenal', 200),
 '4': ('Bayern Munich', 225),
 '5': ('Manchester United', 200)}

STARTING = {'Real Madrid': ['Thibaut Courtois - GK - 89',
                 'Marc Cucurella - LB - 90',
                 'Dean Hujisen - CB - 88',
                 'Ibrahima Konate - CB - 88',
                 'Trent Alexander-Arnold - RB - 88',
                 'Yan Diomande - CM - 89',
                 'Federico Valverde - CM - 89',
                 'Jude Bellingham - CAM - 91',
                 'Rodrygo - RW - 87',
                 'Vinicius Junior - LW - 91',
                 'Kylian Mbappe - ST - 92'],
 'Barcelona': ['Joan Garcia - GK - 88',
               'Alejandro Balde - LB - 87',
               'Eric Garcia - CB - 88',
               'Pau Cubarsi - CB - 89',
               'Jules Kounde - RB - 88',
               'Pedri - CM - 90',
               'Fermin Lopez - CM - 89',
               'Dani Olmo - CAM - 88',
               'Lamine Yamal - RW - 92',
               'Anthony Gordon - LW - 89',
               'Raphinha - ST - 92'],
 'Arsenal': ['David Raya - GK - 88',
             'Jurrien Timber - RB - 87',
             'William Saliba - CB - 89',
             'Gabriel Magalhaes - CB - 88',
             'Riccardo Calafiori - LB - 87',
             'Martin Odegaard - CM - 89',
             'Martin Zubimendi - CM - 87',
             'Declane Rice - CDM - 90',
             'Bukayo Saka - RW - 91',
             'Eberechi Eze - LW - 88',
             'Viktor Gyokeres - ST - 88'],
 'Bayern Munich': ['Manuel Neuer - GK - 89',
                   'Konrad Laimer - RB - 86',
                   'Dayot Upamecano - CB - 88',
                   'Jonathan Tah - CB - 87',
                   'Alphonso Davies - LB - 89',
                   'Joshua Kimmich - CM - 89',
                   'Aleksandar Pavlovic - CM - 86',
                   'Jamal Musiala - CAM - 90',
                   'Michael Olise - RW - 91',
                   'Luis Diaz - LW - 89',
                   'Harry Kane - ST - 92'],
 'Manchester United': ['Senne Lammens - GK - 87',
                       'Diogo Dalot - RB - 86',
                       'Lisandro Martinez - CB - 87',
                       'Matthijs de Ligt - CB - 88',
                       'Patrick Dorgu - LB - 86',
                       'Andrey Santos - CM - 87',
                       'Carlos Baleba - CM - 88',
                       'Bruno Fernandes - CAM - 91',
                       'Bryan Mbeumo - RW - 88',
                       'Matheus Cunha - LW - 88',
                       'Benjamin Sesko - ST - 88']}

BENCH = {'Real Madrid': ['Andriy Lunin - GK - 82',
                 'Fran Garcia - LB - 81',
                 'Raul Asencio - CB - 80',
                 'Dani Ceballos - CM - 82',
                 'Brahim Diaz - RW - 85'],
 'Barcelona': ['Wojciech Szczesny - GK - 82',
               'Gerard Martin - LB - 78',
               'Ronald Araujo - CB - 87',
               'Frenkie de Jong - CM - 88',
               'Ferran Torres - ST - 84'],
 'Arsenal': ['Kepa Arrizabalaga - GK - 80',
             'Ben White - RB - 84',
             'Jakub Kiwior - CB - 80',
             'Mikel Merino - CM - 83',
             'Gabriel Martinelli - LW - 86'],
 'Bayern Munich': ['Sven Ulreich - GK - 75',
                   'Raphael Guerreiro - LB - 82',
                   'Kim Min-jae - CB - 85',
                   'Leon Goretzka - CM - 83',
                   'Serge Gnabry - RW - 84'],
 'Manchester United': ['Altay Bayindir - GK - 76',
                       'Noussair Mazraoui - RB - 84',
                       'Harry Maguire - CB - 81',
                       'Kobbie Mainoo - CM - 83',
                       'Joshua Zirkzee - ST - 82']}

PLAYER_PRICES = {'Kylian Mbappe': 200,
 'Vinicius Junior': 140,
 'Rodrygo': 41,
 'Jude Bellingham': 160,
 'Federico Valverde': 90,
 'Yan Diomande': 110,
 'Trent Alexander-Arnold': 62,
 'Dean Hujisen': 60,
 'Ibrahima Konate': 45,
 'Marc Cucurella': 50,
 'Thibaut Courtois': 15,
 'Lamine Yamal': 220,
 'Pedri': 150,
 'Fermin Lopez': 100,
 'Raphinha': 70,
 'Anthony Gordon': 65,
 'Dani Olmo': 60,
 'Alejandro Balde': 50,
 'Eric Garcia': 40,
 'Pau Cubarsi': 80,
 'Jules Kounde': 60,
 'Joan Garcia': 45,
 'Gabriel Magalhaes': 75,
 'Bukayo Saka': 110,
 'William Saliba': 100,
 'Declane Rice': 120,
 'Martin Odegaard': 67,
 'Viktor Gyokeres': 65,
 'Eberechi Eze': 67,
 'Martin Zubimendi': 75,
 'Jurrien Timber': 70,
 'Riccardo Calafiori': 53,
 'David Raya': 30,
 'Harry Kane': 65,
 'Jamal Musiala': 120,
 'Michael Olise': 140,
 'Luis Diaz': 70,
 'Joshua Kimmich': 40,
 'Dayot Upamecano': 70,
 'Alphonso Davies': 45,
 'Jonathan Tah': 30,
 'Konrad Laimer': 32,
 'Aleksandar Pavlovic': 75,
 'Manuel Neuer': 4,
 'Bruno Fernandes': 35,
 'Benjamin Sesko': 75,
 'Matheus Cunha': 75,
 'Bryan Mbeumo': 75,
 'Carlos Baleba': 55,
 'Kobbie Mainoo': 70,
 'Diogo Dalot': 30,
 'Matthijs de Ligt': 30,
 'Lisandro Martinez': 40,
 'Patrick Dorgu': 35,
 'Senne Lammens': 25,
 'Desire Doue': 130,
 'Antony': 50,
 'Mason Mount': 56,
 'Rasmus Hojlund': 60,
 'Jack Grealish': 45,
 'Enzo Fernandez': 120,
 'Bernardo Silva': 22,
 'Nicolas Jackson': 40,
 'Virgil van Dijk': 15,
 'Ousmane Dembele': 100,
 'Khvicha Kvaratskhelia': 140,
 'Amad Diallo': 45,
 'Takefusa Kubo': 30,
 'Jadon Sancho': 25,
 'Micky van de Ven': 50,
 'Milos Kerkez': 40,
 'Teun Koopmeiners': 40,
 'Rayan Cherki': 45,
 'Lautaro Martinez': 95,
 'Alexis Mac Allister': 100,
 'Victor Osimhen': 75,
 'James Ward-Prowse': 10,
 'Kiernan Dewsbury-Hall': 25,
 'Harvey Elliott': 25,
 'Cristiano Ronaldo': 250,
 'Lionel Messi': 250,
 'Neymar Junior': 250}

PLAYER_RATINGS = {'Desire Doue': 91,
 'Antony': 86,
 'Mason Mount': 87,
 'Rasmus Hojlund': 88,
 'Jack Grealish': 86,
 'Dani Olmo': 88,
 'Enzo Fernandez': 89,
 'Bernardo Silva': 88,
 'Nicolas Jackson': 85,
 'Virgil van Dijk': 90,
 'Ousmane Dembele': 92,
 'Khvicha Kvaratskhelia': 91,
 'Amad Diallo': 86,
 'Takefusa Kubo': 81,
 'Jadon Sancho': 82,
 'Micky van de Ven': 83,
 'Milos Kerkez': 84,
 'Teun Koopmeiners': 85,
 'Rayan Cherki': 85,
 'Lautaro Martinez': 86,
 'Alexis Mac Allister': 87,
 'Victor Osimhen': 88,
 'James Ward-Prowse': 78,
 'Kiernan Dewsbury-Hall': 79,
 'Harvey Elliott': 80,
 'Cristiano Ronaldo': 95,
 'Lionel Messi': 95,
 'Neymar Junior': 95}

PLAYER_POSITIONS = {'Desire Doue': 'LW',
 'James Ward-Prowse': 'CM',
 'Kiernan Dewsbury-Hall': 'CM',
 'Harvey Elliott': 'CAM',
 'Antony': 'RW',
 'Mason Mount': 'CAM',
 'Rasmus Hojlund': 'ST',
 'Jack Grealish': 'LW',
 'Enzo Fernandez': 'CM',
 'Bernardo Silva': 'CAM',
 'Nicolas Jackson': 'ST',
 'Virgil van Dijk': 'CB',
 'Ousmane Dembele': 'RW',
 'Khvicha Kvaratskhelia': 'LW',
 'Amad Diallo': 'RW',
 'Takefusa Kubo': 'RW',
 'Jadon Sancho': 'LW',
 'Micky van de Ven': 'CB',
 'Milos Kerkez': 'LB',
 'Teun Koopmeiners': 'CM',
 'Rayan Cherki': 'CAM',
 'Lautaro Martinez': 'ST',
 'Alexis Mac Allister': 'CM',
 'Victor Osimhen': 'ST',
 'Lionel Messi': 'CAM',
 'Cristiano Ronaldo': 'ST',
 'Neymar Junior': 'LW'}

TRANSFER_MARKET = ['Desire Doue',
 'Antony',
 'Mason Mount',
 'Rasmus Hojlund',
 'Jack Grealish',
 'Enzo Fernandez',
 'Bernardo Silva',
 'Nicolas Jackson',
 'Virgil van Dijk',
 'Ousmane Dembele',
 'Khvicha Kvaratskhelia',
 'Amad Diallo',
 'Takefusa Kubo',
 'Jadon Sancho',
 'Micky van de Ven',
 'Milos Kerkez',
 'Teun Koopmeiners',
 'Rayan Cherki',
 'Lautaro Martinez',
 'Alexis Mac Allister',
 'Victor Osimhen',
 'James Ward-Prowse',
 'Kiernan Dewsbury-Hall',
 'Harvey Elliott',
 'Cristiano Ronaldo',
 'Lionel Messi',
 'Neymar Junior']

# Tỷ lệ thành công: khóa theo cấp hiện tại (0 nghĩa là ép +0 lên +1).
UPGRADE_RATES = {
    0: 99, 1: 90, 2: 80, 3: 60,
    4: 40, 5: 30, 6: 20, 7: 10,
}

# Chi phí ép theo cấp đích, tính theo % giá trị gốc của cầu thủ.
UPGRADE_COSTS = {
    1: 2, 2: 6, 3: 10, 4: 15,
    5: 20, 6: 25, 7: 42, 8: 60,
}

# Khi thất bại, key là cấp thẻ nhận được và value là xác suất %.
UPGRADE_FAILURE_DISTRIBUTION = {
    0: {0: 100},
    1: {0: 100},
    2: {0: 50, 1: 50},
    3: {0: 30, 1: 50, 2: 20},
    4: {0: 20, 1: 35, 2: 35, 3: 10},
    5: {0: 12, 1: 15, 2: 30, 3: 30, 4: 13},
    6: {0: 6, 1: 8, 2: 12, 3: 14, 4: 40, 5: 20},
    7: {0: 1, 1: 2, 2: 4, 3: 13, 4: 15, 5: 45, 6: 20},
}

# OVR tăng theo mốc cấp thẻ thành công, không bị giới hạn ở 99.
UPGRADE_OVR_BONUS = {
    1: 1, 2: 1, 3: 1, 4: 1,
    5: 2, 6: 2, 7: 2, 8: 3,
}

# Hệ số giá trị cộng dồn; mọi mức đều tính từ giá trị gốc.
CARD_VALUE_RATES = {
    0: 1.000, 1: 1.100, 2: 1.300,
    3: 1.650, 4: 2.150, 5: 2.900,
    6: 4.155, 7: 5.760, 8: 8.560,
}

MAX_UPGRADE_LEVEL = 8

PACKS = {'1': {'name': 'Gói Đồng',
       'price': 20,
       'players': ['James Ward-Prowse',
                   'Kiernan Dewsbury-Hall',
                   'Harvey Elliott',
                   'Takefusa Kubo',
                   'Jadon Sancho',
                   'Micky van de Ven',
                   'Milos Kerkez',
                   'Teun Koopmeiners',
                   'Rayan Cherki']},
 '2': {'name': 'Gói Bạc',
       'price': 50,
       'players': ['Antony',
                   'Jack Grealish',
                   'Mason Mount',
                   'Rasmus Hojlund',
                   'Amad Diallo',
                   'Nicolas Jackson',
                   'Lautaro Martinez',
                   'Alexis Mac Allister',
                   'Bernardo Silva',
                   'Enzo Fernandez',
                   'Victor Osimhen']},
 '3': {'name': 'Gói Vàng',
       'price': 100,
       'players': ['Desire Doue',
                   'Mason Mount',
                   'Rasmus Hojlund',
                   'Jack Grealish',
                   'Enzo Fernandez',
                   'Bernardo Silva',
                   'Virgil van Dijk',
                   'Ousmane Dembele',
                   'Khvicha Kvaratskhelia',
                   'Amad Diallo',
                   'Lautaro Martinez',
                   'Alexis Mac Allister',
                   'Victor Osimhen']},
 '4': {'name': 'Gói GOAT', 'price': 500, 'players': ['Cristiano Ronaldo', 'Lionel Messi', 'Neymar Junior']}}

CLUBS = {name: {"budget": budget, "rating": 0} for _, (name, budget) in CLUB_OPTIONS.items()}

def player(name, default_pos="ST", default_rating=80):
    if " - " in name:
        a=name.split(" - "); return {"name":a[0],"position":a[1],"rating":int(a[2]),"level":int(a[3].replace("+", "")) if len(a)>3 else 0}
    return {"name":name,"position":PLAYER_POSITIONS.get(name,default_pos),"rating":PLAYER_RATINGS.get(name,default_rating),"level":0}

def pack_player(p):
    return f"{p['name']} - {p['position']} - {p['rating']} - +{p.get('level', 0)}"

def round_half_up(number, digits=2):
    """Làm tròn kiểu half-up, tránh quy tắc bankers rounding của round()."""
    quantum = Decimal("1").scaleb(-digits)
    return float(Decimal(str(number)).quantize(quantum, rounding=ROUND_HALF_UP))

def player_base_value(p):
    """Giá trị gốc của cầu thủ, không phụ thuộc cấp ép thẻ."""
    base = p.get('market_value')
    if base is None:
        base = PLAYER_PRICES.get(p['name'], max(5, (int(p.get('rating', 80)) - 65) * 3))
    return max(0.0, float(base))

def player_upgrade_ovr(p):
    """Tính OVR hiện tại từ OVR gốc và cấp thẻ; không sửa OVR gốc."""
    try:
        level = int(p.get('level', 0))
    except (TypeError, ValueError):
        level = 0
    level = max(0, min(MAX_UPGRADE_LEVEL, level))
    bonus = sum(UPGRADE_OVR_BONUS.get(step, 0) for step in range(1, level + 1))
    return int(p.get('rating', 80)) + bonus

def upgrade_cost(p, target_level):
    """Chi phí ép cấp đích, tính theo phần trăm giá trị gốc."""
    if target_level not in UPGRADE_COSTS:
        raise ValueError('Cấp ép thẻ không hợp lệ')
    return round_half_up(player_base_value(p) * UPGRADE_COSTS[target_level] / 100)

def value(p):
    """Giá trị hiện tại = giá trị gốc × hệ số cấp thẻ hiện tại."""
    try:
        level = int(p.get('level', 0))
    except (TypeError, ValueError):
        level = 0
    level = max(0, min(MAX_UPGRADE_LEVEL, level))
    return round_half_up(player_base_value(p) * CARD_VALUE_RATES[level])
def create_new_game(club):
    if club not in STARTING: raise ValueError('CLB không hợp lệ')
    starters=[player(x) for x in STARTING[club]]; bench=[player(x) for x in BENCH[club]]
    return {"club":club,"budget":next(budget for _, (name, budget) in CLUB_OPTIONS.items() if name == club),"season":1,"week":1,"points":0,"wins":0,"draws":0,"losses":0,"starting":starters,"bench":bench,"extras":[],"market":copy.deepcopy(TRANSFER_MARKET),"formation":"4-3-3 (Tấn công)","activity":[]}

def normalize_state(st):
    # Migrate legacy saves without resetting progress or existing owned players.
    if not isinstance(st, dict):
        st = {}
    club = st.get('club')
    if 'starting' not in st:
        old = st.pop('players', []) or []
        st['starting'] = old[:11]
        st['bench'] = old[11:]
    st.setdefault('starting', [])
    # Migrate legacy entries and enforce one copy of each player across the whole club.
    # Keep the first copy (starting XI has priority), so a duplicate cannot silently
    # occupy two slots or block match validation.
    seen_names = set()
    def clean_players(items):
        cleaned = []
        for item in (items or []):
            try:
                record = player(item) if isinstance(item, str) else copy.deepcopy(item)
                if not isinstance(record, dict) or not record.get('name'):
                    continue
                name = str(record['name']).strip()
                if not name or name.casefold() in seen_names:
                    continue
                record['name'] = name
                seen_names.add(name.casefold())
                cleaned.append(record)
            except (TypeError, KeyError, ValueError):
                continue
        return cleaned
    st['starting'] = clean_players(st.get('starting'))
    st['bench'] = clean_players(st.get('bench'))
    st['extras'] = clean_players(st.get('extras'))
    # Add default substitutes only when they are not already owned in any group.
    owned_names = {p['name'] for group in ('starting', 'bench', 'extras') for p in st[group]}
    default_bench = [player(x) for x in BENCH.get(club, [])]
    st['bench'].extend(p for p in default_bench if p['name'] not in owned_names)
    st.setdefault('extras', [])
    st.setdefault('market', copy.deepcopy(TRANSFER_MARKET))
    # GOAT players are pack-only, not part of the ordinary transfer market.
    goat_names = set(PACKS['4']['players'])
    st['market'] = [n for n in st['market'] if n not in goat_names]
    # Preserve a valid saved balance; repair only legacy saves with no balance.
    if 'budget' not in st or st['budget'] is None:
        st['budget'] = next((b for _, (n, b) in CLUB_OPTIONS.items() if n == club), 0)
    try:
        st['budget'] = round(max(0.0, float(st['budget'])), 2)
        # Match the original Python game: a new Real Madrid save starts at 300 M€.
        # One-time correction for the current save that was initialized at 180 M€.
        if club == 'Real Madrid' and st['budget'] == 180.0:
            st['budget'] = 300.0
        # Legacy repair: balances are stored in million euros (M€).
        # Older saves may contain the same balance as raw euros by mistake.
        if st['budget'] > 100_000:
            st['budget'] = round(st['budget'] / 1_000_000, 2)
    except (TypeError, ValueError):
        st['budget'] = next((b for _, (n, b) in CLUB_OPTIONS.items() if n == club), 0)
    st.setdefault('season', 1); st.setdefault('week', 1)
    st.setdefault('points', 0); st.setdefault('wins', 0); st.setdefault('draws', 0); st.setdefault('losses', 0)
    st.setdefault('formation', '4-3-3 (Tấn công)');
    if st.get('formation') == '4-3-3': st['formation'] = '4-3-3 (Tấn công)'; st.setdefault('activity', []); st.setdefault('match_history', [])
    if not isinstance(st['match_history'], list): st['match_history'] = []
    st['match_history'] = st['match_history'][:5]
    return st

def all_players(st): return st['starting']+st['bench']+st['extras']
def get_dashboard(st):
    arr=st['starting']; return {"club":st['club'],"budget":st['budget'],"season":st['season'],"week":st['week'],"points":st['points'],"wins":st['wins'],"draws":st['draws'],"losses":st['losses'],"formation":st['formation'],"squad_size":len(all_players(st)),"average_rating":round(sum(player_upgrade_ovr(p) for p in arr)/max(1,len(arr)),1),"total_value":round(sum(value(p) for p in all_players(st)),2)}

def _match_player_name(p):
    return p.get('name', 'Cầu thủ') if isinstance(p, dict) else str(p).split(' - ')[0]

def _match_position(p):
    return p.get('position', 'ST') if isinstance(p, dict) else (str(p).split(' - ')[1] if len(str(p).split(' - ')) > 1 else 'ST')

def _match_rating(p):
    if isinstance(p, dict):
        return player_upgrade_ovr(p)
    parts = str(p).split(' - ')
    try: return int(parts[2])
    except (IndexError, ValueError): return 80

def _weighted_player(squad, weights):
    return random.choices(squad, weights=weights, k=1)[0]

def simulate_match(st):
    """Simulate a match with chronological events and red-card-aware scoring."""
    from datetime import datetime, timezone
    opponents = [club for club in STARTING if club != st['club']]
    opponent = random.choice(opponents)
    my_squad = list(st.get('starting') or [])
    opponent_squad = [player(x) for x in STARTING[opponent]]
    if len(my_squad) != 11:
        raise ValueError('Cần đủ 11 cầu thủ đá chính')

    my_ovr = sum(_match_rating(p) for p in my_squad) / len(my_squad)
    opponent_ovr = sum(_match_rating(p) for p in opponent_squad) / len(opponent_squad)

    def scoring_weight(p):
        base = {'ST':1.50,'LW':1.35,'RW':1.35,'CAM':1.20,'CM':.90,'CDM':.65,'LB':.40,'RB':.40,'CB':.30,'GK':.01}.get(_match_position(p),.5)
        return max(.01, base * (1 + (_match_rating(p)-80)*.04))
    def own_goal_weight(p):
        base = {'GK':.15,'CB':.45,'LB':.35,'RB':.35,'CDM':.20}.get(_match_position(p),.01)
        return max(.01, base * max(.1, 1 - (_match_rating(p)-80)*.025))
    def weighted_pick(squad, weights):
        return random.choices(squad, weights=weights, k=1)[0]

    events, used_minutes = [], set()
    def minute():
        available = [m for m in range(1, 91) if m not in used_minutes]
        if not available: return 90
        chosen = random.choice(available); used_minutes.add(chosen); return chosen

    # Cards are assigned first so later scoring opportunities can exclude sent-off players.
    team_data = [
        {'club': st['club'], 'squad': my_squad, 'defenders': [p for p in my_squad if _match_position(p) in ('GK','CB','LB','RB')] or my_squad, 'is_home': True},
        {'club': opponent, 'squad': opponent_squad, 'defenders': [p for p in opponent_squad if _match_position(p) in ('GK','CB','LB','RB')] or opponent_squad, 'is_home': False},
    ]
    red_off = {st['club']: {}, opponent: {}}
    for team in team_data:
        squad, club = team['squad'], team['club']
        if random.random() < .35:
            card_player = random.choice(squad)
            events.append({'minute': minute(), 'type':'card', 'team':club, 'player':_match_player_name(card_player), 'detail':'Thẻ vàng 🟨'})
        if random.random() < .10:
            card_player = random.choice(squad)
            red_minute = minute()
            red_off[club][_match_player_name(card_player)] = red_minute
            events.append({'minute':red_minute, 'type':'card', 'team':club, 'player':_match_player_name(card_player), 'detail':'Thẻ đỏ 🟥'})

    # A sending-off reduces that team's scoring chance; the removed probability
    # is transferred to the opponent, keeping the two chances balanced.
    red_home = len(red_off[st['club']])
    red_away = len(red_off[opponent])
    base_my = max(.10, min(.55, .30 + (my_ovr-opponent_ovr)*.015))
    base_opp = max(.10, min(.55, .30 + (opponent_ovr-my_ovr)*.015))
    penalty_my = min(.20, .08 * red_home)
    penalty_opp = min(.20, .08 * red_away)
    my_chance = max(.05, min(.70, base_my - penalty_my + penalty_opp))
    opp_chance = max(.05, min(.70, base_opp - penalty_opp + penalty_my))

    opp_gk = next((p for p in opponent_squad if _match_position(p)=='GK'), None)
    my_gk = next((p for p in my_squad if _match_position(p)=='GK'), None)
    if opp_gk: my_chance *= max(.45, 1-(_match_rating(opp_gk)-80)*.015)
    if my_gk: opp_chance *= max(.45, 1-(_match_rating(my_gk)-80)*.015)

    goals_by_team = {st['club']: 0, opponent: 0}
    def eligible_players(squad, club, event_minute):
        sent_off = red_off[club]
        return [p for p in squad if sent_off.get(_match_player_name(p), 999) > event_minute]
    def add_goal(team, squad, detail='Bàn thắng', scorer_pool=None):
        event_minute = minute()
        eligible = scorer_pool if scorer_pool is not None else eligible_players(squad, team, event_minute)
        if not eligible:
            return False
        scorer = weighted_pick(eligible, [scoring_weight(p) for p in eligible])
        goals_by_team[team] += 1
        events.append({'minute':event_minute, 'type':'goal', 'team':team, 'player':_match_player_name(scorer), 'detail':detail})
        return True

    for team, chance in [(st['club'], my_chance), (opponent, opp_chance)]:
        squad = my_squad if team == st['club'] else opponent_squad
        for _ in range(random.randint(3,7)):
            if random.random() < chance:
                add_goal(team, squad)
        if random.random() < .30:
            add_goal(team, squad, 'Penalty')

    for team in team_data:
        club, defenders = team['club'], team['defenders']
        if random.random() < .20:
            event_minute = minute()
            eligible_defenders = eligible_players(defenders, club, event_minute)
            if eligible_defenders:
                own_goal_player = weighted_pick(eligible_defenders, [own_goal_weight(p) for p in eligible_defenders])
                scoring_team = opponent if club == st['club'] else st['club']
                goals_by_team[scoring_team] += 1
                events.append({'minute':event_minute, 'type':'goal', 'team':scoring_team,
                               'player':_match_player_name(own_goal_player),
                               'detail':f'Phản lưới nhà (OG) - {club}'})

    events.sort(key=lambda e:e['minute'])
    my_goals, opponent_goals = goals_by_team[st['club']], goals_by_team[opponent]
    yellow=sum(1 for e in events if e['type']=='card' and 'vàng' in e['detail'])
    red=sum(1 for e in events if e['type']=='card' and 'đỏ' in e['detail'])
    penalties=sum(1 for e in events if e['type']=='goal' and e['detail']=='Penalty')
    own_goals=sum(1 for e in events if e['type']=='goal' and 'OG' in e['detail'])
    result='THẮNG' if my_goals>opponent_goals else 'HÒA' if my_goals==opponent_goals else 'THUA'
    reward=20 if my_goals>opponent_goals else 10 if my_goals==opponent_goals else 5
    st['budget']=round(float(st.get('budget',0))+reward,2); st['week']=int(st.get('week',1))+1
    if my_goals>opponent_goals: st['wins']=int(st.get('wins',0))+1; st['points']=int(st.get('points',0))+3
    elif my_goals==opponent_goals: st['draws']=int(st.get('draws',0))+1; st['points']=int(st.get('points',0))+1
    else: st['losses']=int(st.get('losses',0))+1
    match={'id':datetime.now(timezone.utc).isoformat(),'club':st['club'],'opponent':opponent,'score_home':my_goals,'score_away':opponent_goals,'score':f'{my_goals} - {opponent_goals}','result':result,'reward':reward,'my_ovr':round(my_ovr,1),'opponent_ovr':round(opponent_ovr,1),'events':events,'stats':{'goals_home':my_goals,'goals_away':opponent_goals,'penalties':penalties,'own_goals':own_goals,'yellow_cards':yellow,'red_cards':red}}
    st.setdefault('match_history',[]).insert(0,match)
    st['match_history']=st['match_history'][:5]
    return match
