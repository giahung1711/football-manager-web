"""Daily quest definitions and state helpers for FOOTBALL MANAGER."""
import copy
import random
from datetime import datetime
from zoneinfo import ZoneInfo

DAILY_QUEST_REWARDS = {
    'completion': {'pc': 500, 'pg': 4000, 'cards': 4},
    'special': {'pc': 750, 'pg': 5000, 'cards': 5},
}

# PC rewards are stored in millions, matching the existing club budget unit.
DAILY_QUEST_CATALOG = [
    ('q01','Chơi 1 trận đấu','matches',1,20,0,0),
    ('q02','Chơi 2 trận đấu','matches',2,40,0,0),
    ('q03','Chơi 3 trận đấu','matches',3,60,0,0),
    ('q04','Thắng 1 trận đấu','wins',1,40,0,0),
    ('q05','Thắng 2 trận đấu','wins',2,70,0,0),
    ('q06','Thắng 3 trận đấu','wins',3,100,0,0),
    ('q07','Ghi 3 bàn thắng','goals',3,30,0,0),
    ('q08','Ghi 5 bàn thắng','goals',5,50,0,0),
    ('q09','Ghi 10 bàn thắng','goals',10,80,0,0),
    ('q10','Giữ sạch lưới 1 trận','clean_sheets',1,40,0,0),
    ('q11','Giữ sạch lưới 2 trận','clean_sheets',2,70,0,0),
    ('q12','Ghi bàn bằng 3 cầu thủ khác nhau','unique_scorers',3,50,0,0),
    ('q13','Thắng cách biệt ít nhất 2 bàn','win_by_two',1,50,0,0),
    ('q14','Hoàn thành 5 trận đấu','matches',5,100,500,0),
    ('q15','Thắng 5 trận đấu','wins',5,150,1000,0),
    ('q16','Ép thẻ 1 lần','upgrade_attempts',1,20,0,0),
    ('q17','Ép thẻ 3 lần','upgrade_attempts',3,50,0,0),
    ('q18','Ép thẻ 5 lần','upgrade_attempts',5,80,0,0),
    ('q19','Ép thẻ thành công 1 lần','upgrade_successes',1,40,0,0),
    ('q20','Ép thẻ thành công 2 lần','upgrade_successes',2,70,0,0),
    ('q21','Ép thẻ thành công 3 lần','upgrade_successes',3,100,500,0),
    ('q22','Ép thẻ lên cấp +3','reach_3',1,50,0,0),
    ('q23','Ép thẻ lên cấp +5','reach_5',1,80,500,0),
    ('q24','Ép thẻ lên cấp +7','reach_7',1,120,1000,0),
    ('q25','Ép thẻ thành công lên cấp +6','reach_6',1,160,1500,0),
    ('q26','Mua 1 cầu thủ trên TTCN','buys',1,30,0,0),
    ('q27','Mua 2 cầu thủ trên TTCN','buys',2,60,0,0),
    ('q28','Bán 1 cầu thủ','sells',1,30,0,0),
    ('q29','Bán 2 cầu thủ','sells',2,60,0,0),
    ('q30','Mua và bán ít nhất 1 cầu thủ','buy_and_sell',1,50,0,0),
    ('q31','Mở 1 gói cầu thủ','packs',1,30,0,0),
    ('q32','Mở 3 gói cầu thủ','packs',3,70,500,0),
    ('q33','Mở 5 gói cầu thủ','packs',5,100,1000,0),
    ('q34','Bán 3 cầu thủ trên TTCN','sells',3,120,1000,0),
    ('q35','Mở 7 gói cầu thủ','packs',7,140,1250,0),
    ('q36','Sử dụng tổng cộng 2.000 PG','pg_spent',2000,50,0,0),
    ('q37','Chi tiêu tổng cộng 10 triệu PC','pc_spent',10,30,250,0),
    ('q38','Ép thẻ thành công 5 lần','upgrade_successes',5,150,1000,1),
    ('q39','Thắng 3 trận liên tiếp','win_streak',3,100,1000,1),
    ('q40','Mở 10 gói cầu thủ','packs',10,150,1500,1),
]

SPECIAL_QUEST_CATALOG = [
    {'id':'s01','title':'Ép thẻ thành công lên +8','metric':'special_plus8','target':1},
    {'id':'s02','title':'Mở gói nhận được cầu thủ OVR 101 trở lên','metric':'special_ovr101','target':1},
    {'id':'s03','title':'Thắng 8 trận liên tiếp','metric':'special_win_streak8','target':8},
    {'id':'s04','title':'Ép thẻ thành công 6 lần liên tiếp ở các cấp thẻ trên +3','metric':'special_upgrade_streak6','target':6},
    {'id':'s05','title':'Thắng 5 trận liên tiếp, mỗi trận không thủng lưới quá 1 bàn','metric':'special_win_concede_streak5','target':5},
    {'id':'s08','title':'Thắng 100 trận trong ngày','metric':'special_wins100','target':100},
]


def _vn_today():
    return datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat()


def ensure_daily_quests(state):
    daily = state.get('daily_quests')
    today = _vn_today()
    if not isinstance(daily, dict) or daily.get('date') != today:
        chosen = random.sample(DAILY_QUEST_CATALOG, 10)
        state['daily_quests'] = {
            'date': today,
            'missions': [
                {'id': q[0], 'title': q[1], 'metric': q[2], 'target': q[3],
                 'pc': q[4], 'pg': q[5], 'cards': q[6], 'progress': 0, 'claimed': False}
                for q in chosen
            ],
            'special': copy.deepcopy(random.choice(SPECIAL_QUEST_CATALOG)) if random.random() < .20 else None,
            'special_progress': 0,
            'special_claimed': False,
            'completion_claimed': False,
            'counters': {'unique_scorers': [], 'buy_count': 0, 'sell_count': 0,
                         'win_streak': 0, 'special_upgrade_streak': 0,
                         'special_win_concede_streak': 0},
        }
        return True
    daily.setdefault('counters', {})
    daily['counters'].setdefault('unique_scorers', [])
    return False


def update_daily_quests(state, event, data=None):
    if not event:
        return
    ensure_daily_quests(state)
    daily = state['daily_quests']
    counters = daily.setdefault('counters', {})
    data = data or {}

    if event == 'match':
        counters['matches'] = counters.get('matches', 0) + 1
        counters['goals'] = counters.get('goals', 0) + int(data.get('goals', 0))
        counters['wins'] = counters.get('wins', 0) + (1 if data.get('won') else 0)
        counters['clean_sheets'] = counters.get('clean_sheets', 0) + (1 if data.get('conceded', 0) == 0 else 0)
        counters['win_by_two'] = counters.get('win_by_two', 0) + (1 if data.get('won') and data.get('goal_diff', 0) >= 2 else 0)
        scorers = set(counters.get('unique_scorers', []))
        scorers.update(data.get('scorers', []))
        counters['unique_scorers'] = list(scorers)
        counters['win_streak'] = counters.get('win_streak', 0) + 1 if data.get('won') else 0
        counters['special_win_concede_streak'] = counters.get('special_win_concede_streak', 0) + 1 if data.get('won') and data.get('conceded', 0) <= 1 else 0
    elif event == 'upgrade':
        counters['upgrade_attempts'] = counters.get('upgrade_attempts', 0) + 1
        counters['pc_spent'] = counters.get('pc_spent', 0) + float(data.get('pc_spent', 0))
        if data.get('success'):
            counters['upgrade_successes'] = counters.get('upgrade_successes', 0) + 1
            for level in (3, 5, 6, 7):
                if data.get('new_level', 0) >= level:
                    counters[f'reach_{level}'] = 1
        if data.get('success') and data.get('old_level', 0) >= 3:
            counters['special_upgrade_streak'] = counters.get('special_upgrade_streak', 0) + 1
        else:
            counters['special_upgrade_streak'] = 0
        if data.get('success') and data.get('new_level', 0) >= 8:
            counters['special_plus8'] = 1
    elif event == 'buy':
        counters['buy_count'] = counters.get('buy_count', 0) + 1
        counters['buys'] = counters.get('buys', 0) + 1
        counters['pc_spent'] = counters.get('pc_spent', 0) + float(data.get('pc_spent', 0))
    elif event == 'sell':
        counters['sell_count'] = counters.get('sell_count', 0) + 1
        counters['sells'] = counters.get('sells', 0) + 1
        counters['sale_value'] = counters.get('sale_value', 0) + float(data.get('sale_value', 0))
    elif event == 'pack':
        counters['packs'] = counters.get('packs', 0) + 1
        counters['pc_spent'] = counters.get('pc_spent', 0) + float(data.get('pc_spent', 0))
        counters['pg_spent'] = counters.get('pg_spent', 0) + int(data.get('pg_spent', 0))
        if int(data.get('rating', 0)) >= 101:
            counters['special_ovr101'] = 1

    if counters.get('buy_count', 0) >= 1 and counters.get('sell_count', 0) >= 1:
        counters['buy_and_sell'] = 1
    counters['special_win_streak8'] = counters.get('win_streak', 0)
    counters['special_win_concede_streak5'] = counters.get('special_win_concede_streak', 0)
    counters['special_upgrade_streak6'] = counters.get('special_upgrade_streak', 0)
    counters['special_wins100'] = counters.get('wins', 0)

    for mission in daily.get('missions', []):
        metric = mission['metric']
        if metric == 'win_streak':
            mission['progress'] = counters.get('win_streak', 0)
        elif metric == 'unique_scorers':
            mission['progress'] = len(counters.get('unique_scorers', []))
        elif metric == 'buy_and_sell':
            mission['progress'] = counters.get('buy_and_sell', 0)
        else:
            mission['progress'] = counters.get(metric, 0)

    special = daily.get('special')
    if special:
        daily['special_progress'] = counters.get(special['metric'], 0)


def grant_quest_reward(state, reward):
    state['budget'] = round(float(state.get('budget', 0)) + float(reward.get('pc', 0)), 2)
    state['pg_balance'] = int(state.get('pg_balance', 0)) + int(reward.get('pg', 0))
    if reward.get('cards', 0):
        inventory = state.setdefault('inventory', {})
        inventory['Thẻ bảo vệ'] = int(inventory.get('Thẻ bảo vệ', 0) or 0) + int(reward['cards'])
