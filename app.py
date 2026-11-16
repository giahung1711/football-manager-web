import os, random, copy, math, secrets, hmac
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, GameSave, FriendRequest, Friendship, FriendlyChallenge, A1CupSeason
from marketplace import player_market_bp
from player_metadata import enrich_player
from daily_quests import DAILY_QUEST_REWARDS, ensure_daily_quests, update_daily_quests, grant_quest_reward
from game_engine import (CLUBS, create_new_game, get_dashboard, all_players, normalize_state,
                         TRANSFER_MARKET, PLAYER_PRICES, PLAYER_RATINGS, PLAYER_POSITIONS,
                         PACKS, UPGRADE_RATES, UPGRADE_COSTS, CARD_VALUE_RATES, BALLON_DOR_VALUES, CHRISTMAS_2026_PLAYERS, SWEET_CANDY_PLAYERS, SWEET_CANDY_VALUES, CARD_SEASON_OPTIONS, UPGRADE_FAILURE_DISTRIBUTION, MAX_UPGRADE_LEVEL, upgrade_cost, value, player, simulate_match)

app = Flask(__name__)
app.register_blueprint(player_market_bp)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-secret-key-before-deploying')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///football_manager.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 3 * 1024 * 1024
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)
db.init_app(app)
login_manager = LoginManager(app); login_manager.login_view = 'login'
@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))
with app.app_context():
    db.create_all()
    # Lightweight migration for existing SQLite/PostgreSQL databases.
    from sqlalchemy import inspect, text
    user_columns = {column['name'] for column in inspect(db.engine).get_columns('user')}
    if 'is_admin' not in user_columns:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE \"user\" ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE'))
    if 'last_seen_at' not in user_columns:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE \"user\" ADD COLUMN last_seen_at TIMESTAMP NULL'))
    # The sole admin is provisioned from private hosting environment variables.
    # Never expose an in-app admin registration or public first-claim setup page.
    admin_username = os.environ.get('ADMIN_USERNAME', '').strip()
    admin_password = os.environ.get('ADMIN_PASSWORD', '')
    if admin_username and admin_password:
        admin = User.query.filter_by(username=admin_username).first()
        if admin is None:
            admin = User(username=admin_username, is_admin=True)
            admin.set_password(admin_password)
            db.session.add(admin)
        else:
            admin.is_admin = True
        # Always align the provisioned account password with the private host setting.
        admin.set_password(admin_password)
        # Enforce exactly one admin account.
        User.query.filter(User.id != admin.id).update({User.is_admin: False})
        db.session.commit()

# Start the persistent server-side A1 Cup clock after database tables/migrations are ready.
def admin_required(view):
    from functools import wraps
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            flash('Bạn không có quyền truy cập khu vực Admin.')
            return redirect(url_for('dashboard'))
        return view(*args, **kwargs)
    return wrapped

def format_money(amount):
    pc_units = int(round(float(amount or 0) * 1_000_000))
    return f"🪙 {pc_units:,}".replace(',', '.') + ' PC'

app.jinja_env.filters['money'] = format_money

@app.context_processor
def inject_admin_csrf():
    if '_admin_csrf' not in session:
        session['_admin_csrf'] = secrets.token_urlsafe(32)
    return {'admin_csrf_token': session['_admin_csrf']}

def valid_admin_csrf():
    supplied = request.form.get('csrf_token', '')
    expected = session.get('_admin_csrf', '')
    return bool(supplied and expected and hmac.compare_digest(supplied, expected))

def current_save(): return GameSave.query.filter_by(user_id=current_user.id).first()
def load_state(save):
    # Always detach JSON state before mutation; SQLAlchemy JSON does not track in-place edits.
    original = copy.deepcopy(save.state or {})
    state = normalize_state(copy.deepcopy(original))
    state.setdefault('inventory', {})
    try:
        state['pg_balance'] = max(0, int(state.get('pg_balance', 0) or 0))
    except (TypeError, ValueError):
        state['pg_balance'] = 0
    state.setdefault('upgrade_history', [])
    if state != original:
        save.state = copy.deepcopy(state)
        db.session.commit()
    return state
def persist(save,state):
    save.state = copy.deepcopy(state)
    db.session.add(save)
    db.session.commit()
def page(save, tab='overview', extra=None):
    st=load_state(save)
    if ensure_daily_quests(st):
        persist(save, st)
    # Player metadata is local/Admin-curated only; no external football API is called.
    for group in ('starting', 'bench', 'extras'):
        st[group] = [enrich_player(p) for p in st.get(group, [])]
    market_items=[]
    # Transfer-market listings use the game's built-in data and do not depend on an external API.
    if tab == 'transfers':
        for n in st.get('market', []):
            if n in PACKS['4']['players']:
                continue
            market_items.append({'name':n,'position':PLAYER_POSITIONS.get(n,'ST'),'rating':PLAYER_RATINGS.get(n,80),'price':PLAYER_PRICES.get(n,0)})
    match_popup=session.pop('last_match_result', None)
    ballon_reveal = st.pop('ballon_reveal', None)
    ballon_reveal_meta = enrich_player(ballon_reveal) if ballon_reveal else None
    if ballon_reveal:
        persist(save, st)
    return render_template('game.html', state=st, data=get_dashboard(st), tab=tab, players=all_players(st), match_popup=match_popup, profile_matches=int(st.get('wins', 0) or 0)+int(st.get('draws', 0) or 0)+int(st.get('losses', 0) or 0), profile_win_rate=round(100*int(st.get('wins', 0) or 0)/max(1,int(st.get('wins', 0) or 0)+int(st.get('draws', 0) or 0)+int(st.get('losses', 0) or 0)),1), daily_quests=st.get('daily_quests', {}), daily_completed_count=sum(1 for q in st.get('daily_quests', {}).get('missions', []) if int(q.get('progress', 0)) >= int(q.get('target', 1))),
                           prices={p['name']:value(p) for p in all_players(st)}, player_value=value, packs=PACKS,
                           market=st['market'], market_items=market_items, ballon_reveal=ballon_reveal, ballon_reveal_meta=ballon_reveal_meta, sweet_candy_players=SWEET_CANDY_PLAYERS, christmas_players=CHRISTMAS_2026_PLAYERS, ballon_request_id=secrets.token_urlsafe(18), upgrade_rates=UPGRADE_RATES, upgrade_costs=UPGRADE_COSTS, extra=extra)

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('admin_panel' if current_user.is_admin else 'dashboard'))
    return render_template('home.html')
@app.route('/register',methods=['GET','POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method=='POST':
        u=request.form.get('username','').strip(); p=request.form.get('password','')
        if len(u)<3: flash('Tên tài khoản phải có ít nhất 3 ký tự.')
        elif len(p)<8: flash('Mật khẩu phải có ít nhất 8 ký tự.')
        elif User.query.filter_by(username=u).first(): flash('Tên tài khoản đã được sử dụng.')
        else:
            user=User(username=u); user.set_password(p); db.session.add(user); db.session.commit(); login_user(user); return redirect(url_for('choose_club'))
    return render_template('auth.html',mode='register')
@app.route('/login',methods=['GET','POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method=='POST':
        user=User.query.filter_by(username=request.form.get('username','').strip()).first()
        if user and user.check_password(request.form.get('password','')):
            login_user(user)
            return redirect(url_for('admin_panel' if user.is_admin else 'dashboard'))
        flash('Tên tài khoản hoặc mật khẩu không đúng.')
    return render_template('auth.html',mode='login')
@app.post('/logout')
@login_required
def logout(): logout_user(); return redirect(url_for('home'))
@app.route('/choose-club',methods=['GET','POST'])
@login_required
def choose_club():
    save=current_save()
    if save: return redirect(url_for('dashboard'))
    if request.method=='POST':
        club=request.form.get('club')
        if club not in CLUBS: flash('CLB không hợp lệ.')
        else:
            save=GameSave(user_id=current_user.id,state=create_new_game(club)); db.session.add(save); db.session.commit(); return redirect(url_for('dashboard'))
    return render_template('choose_club.html',clubs=CLUBS)
@app.route('/dashboard')
@login_required
def dashboard():
    save=current_save()
    return redirect(url_for('choose_club')) if not save else page(save)
@app.post('/profile/club-name')
@login_required
def profile_change_club_name():
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang.')
        return redirect(url_for('dashboard'))
    if current_user.is_admin:
        return redirect(url_for('admin_panel'))
    save = current_save()
    if not save:
        return redirect(url_for('choose_club'))
    new_name = request.form.get('club_name', '').strip()
    if not new_name or len(new_name) > 28:
        flash('Tên CLB phải có từ 1 đến 28 ký tự.')
        return redirect(url_for('dashboard'))
    state = load_state(save)
    if new_name == (state.get('custom_club_name') or state.get('club')):
        flash('Tên CLB không thay đổi, bạn chưa bị trừ PG.')
        return redirect(url_for('dashboard'))
    balance = int(state.get('pg_balance', 0) or 0)
    if balance < 20000:
        flash('Không đủ PG. Đổi tên CLB cần 20.000 PG.')
        return redirect(url_for('dashboard'))
    state['pg_balance'] = balance - 20000
    state['custom_club_name'] = new_name
    persist(save, state)
    flash(f'Đổi tên CLB thành công: {new_name}. Đã trừ 20.000 PG.')
    return redirect(url_for('dashboard'))

@app.post('/profile/note')
@login_required
def profile_update_note():
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang.')
        return redirect(url_for('dashboard'))
    if current_user.is_admin:
        return redirect(url_for('admin_panel'))
    save = current_save()
    if not save:
        return redirect(url_for('choose_club'))
    state = load_state(save)
    state['profile_note'] = request.form.get('note', '').strip()[:100]
    persist(save, state)
    flash('Đã cập nhật ghi chú hồ sơ.')
    return redirect(url_for('dashboard'))

@app.post('/profile/avatar')
@login_required
def profile_upload_avatar():
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang.')
        return redirect(url_for('dashboard'))
    if current_user.is_admin:
        return redirect(url_for('admin_panel'))
    save = current_save()
    if not save:
        return redirect(url_for('choose_club'))
    upload = request.files.get('avatar')
    if not upload or not upload.filename:
        flash('Anh chưa chọn ảnh đại diện.')
        return redirect(url_for('dashboard'))
    ext = upload.filename.rsplit('.', 1)[-1].lower() if '.' in upload.filename else ''
    if ext not in {'png', 'jpg', 'jpeg', 'webp'}:
        flash('Ảnh đại diện chỉ hỗ trợ PNG, JPG hoặc WEBP.')
        return redirect(url_for('dashboard'))
    upload.stream.seek(0, os.SEEK_END)
    size = upload.stream.tell()
    upload.stream.seek(0)
    if size <= 0 or size > 2 * 1024 * 1024:
        flash('Ảnh đại diện phải nhỏ hơn hoặc bằng 2 MB.')
        return redirect(url_for('dashboard'))
    upload_dir = os.path.join(app.static_folder, 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    filename = f'profile_{current_user.id}.{ext}'
    # Remove an older avatar extension for this account.
    for old_ext in ('png', 'jpg', 'jpeg', 'webp'):
        old_path = os.path.join(upload_dir, f'profile_{current_user.id}.{old_ext}')
        if os.path.exists(old_path):
            os.remove(old_path)
    upload.save(os.path.join(upload_dir, filename))
    state = load_state(save)
    state['profile_avatar'] = url_for('static', filename=f'uploads/{filename}')
    persist(save, state)
    flash('Đã cập nhật ảnh đại diện.')
    return redirect(url_for('dashboard'))

@app.route('/leaderboard')
@login_required
def leaderboard():
    category = request.args.get('category', 'ovr')
    if category not in {'ovr', 'value', 'win_rate'}:
        category = 'ovr'
    entries = []
    for account in User.query.filter_by(is_admin=False).order_by(User.id.asc()).all():
        save = GameSave.query.filter_by(user_id=account.id).first()
        if not save:
            continue
        state = load_state(save)
        data = get_dashboard(state)
        matches = int(data.get('matches_played', 0) or 0)
        entry = {
            'username': account.username,
            'club': data.get('club', 'Chưa chọn CLB'),
            'ovr': float(data.get('average_rating', 0) or 0),
            'value': float(data.get('squad_value', data.get('total_value', 0)) or 0),
            'matches': matches,
            'wins': int(data.get('wins', 0) or 0),
            'win_rate': float(data.get('win_rate', 0) or 0),
        }
        if category == 'ovr' and entry['ovr'] > 97:
            entries.append(entry)
        elif category == 'value':
            entries.append(entry)
        elif category == 'win_rate' and matches > 100:
            entries.append(entry)
    sort_key = {'ovr': 'ovr', 'value': 'value', 'win_rate': 'win_rate'}[category]
    entries.sort(key=lambda item: (item[sort_key], item['matches'], item['username'].casefold()), reverse=True)
    return render_template('leaderboard.html', entries=entries, category=category)


@app.route('/<tab>')
@login_required
def game_tab(tab):
    if tab not in {'squad','transfers','shop','upgrade','tactics','finance','matches','daily'}: return redirect(url_for('dashboard'))
    save=current_save(); return redirect(url_for('choose_club')) if not save else page(save,tab)
@app.post('/daily-quests/claim')
@login_required
def daily_quest_claim():
    save = current_save()
    if not save:
        return redirect(url_for('choose_club'))
    state = load_state(save)
    ensure_daily_quests(state)
    daily = state['daily_quests']
    quest_id = request.form.get('quest_id', '')
    mission = next((q for q in daily.get('missions', []) if q.get('id') == quest_id), None)
    if not mission or mission.get('claimed') or int(mission.get('progress', 0)) < int(mission.get('target', 1)):
        flash('Nhiệm vụ chưa hoàn thành hoặc phần thưởng đã được nhận.')
    else:
        grant_quest_reward(state, mission)
        mission['claimed'] = True
        flash(f"Đã nhận thưởng nhiệm vụ: +{mission['pc']}M PC, +{mission['pg']:,} PG, +{mission['cards']} Thẻ bảo vệ.")
    persist(save, state)
    return redirect(url_for('game_tab', tab='daily'))


@app.post('/daily-quests/claim-bonus')
@login_required
def daily_quest_claim_bonus():
    save = current_save()
    if not save:
        return redirect(url_for('choose_club'))
    state = load_state(save)
    ensure_daily_quests(state)
    daily = state['daily_quests']
    if daily.get('completion_claimed') or not all(int(q.get('progress', 0)) >= int(q.get('target', 1)) for q in daily.get('missions', [])):
        flash('Bạn cần hoàn thành đủ 10 nhiệm vụ thường trước khi nhận thưởng mốc ngày.')
    else:
        grant_quest_reward(state, DAILY_QUEST_REWARDS['completion'])
        daily['completion_claimed'] = True
        flash('Đã nhận thưởng hoàn thành 10/10: 500M PC, 4.000 PG và 4 Thẻ bảo vệ!')
    persist(save, state)
    return redirect(url_for('game_tab', tab='daily'))


@app.post('/daily-quests/claim-special')
@login_required
def daily_quest_claim_special():
    save = current_save()
    if not save:
        return redirect(url_for('choose_club'))
    state = load_state(save)
    ensure_daily_quests(state)
    daily = state['daily_quests']
    special = daily.get('special')
    if not special or daily.get('special_claimed') or int(daily.get('special_progress', 0)) < int(special.get('target', 1)):
        flash('Nhiệm vụ đặc biệt chưa hoàn thành hoặc phần thưởng đã được nhận.')
    else:
        grant_quest_reward(state, DAILY_QUEST_REWARDS['special'])
        daily['special_claimed'] = True
        flash('Đã nhận thưởng nhiệm vụ đặc biệt: 750M PC, 5.000 PG và 5 Thẻ bảo vệ!')
    persist(save, state)
    return redirect(url_for('game_tab', tab='daily'))


@app.route('/admin', methods=['GET'])
@admin_required
def admin_panel():
    users = User.query.order_by(User.created_at.desc()).all()
    player_names = set(PLAYER_RATINGS) | set(PLAYER_POSITIONS) | set(TRANSFER_MARKET)
    # Mùa thẻ tự lấy từ dữ liệu cầu thủ đang có trong đội hình và hòm thư.
    card_seasons = set(CARD_SEASON_OPTIONS)
    for save in GameSave.query.all():
        state = save.state or {}
        for group in ('starting', 'bench', 'extras'):
            for p in state.get(group, []):
                if p.get('name'):
                    player_names.add(p.get('name'))
                season = str(p.get('card_season') or '').strip()
                if season:
                    card_seasons.add(season)
                if p.get('event_card') == 'ballon_dor':
                    card_seasons.add('Ballon D’or')
        for mail in state.get('mailbox', []):
            gifted = mail.get('player') or {}
            season = str(gifted.get('card_season') or '').strip()
            if season:
                card_seasons.add(season)
            if gifted.get('event_card') == 'ballon_dor':
                card_seasons.add('Ballon D’or')
    return render_template('admin.html', users=users, player_names=sorted(player_names),
                           card_seasons=sorted(card_seasons, key=lambda x: (x != 'Thường', x.casefold())))

@app.post('/admin/gift')
@admin_required
def admin_gift():
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang Admin.')
        return redirect(url_for('admin_panel'))
    try:
        user_id = int(request.form.get('user_id', ''))
        recipient = db.session.get(User, user_id)
        if not recipient:
            raise ValueError('Không tìm thấy tài khoản nhận quà.')
        save = GameSave.query.filter_by(user_id=recipient.id).first()
        if not save:
            raise ValueError('Tài khoản này chưa chọn CLB và chưa có dữ liệu game.')

        name = request.form.get('player_name', '').strip()
        if not name or len(name) > 80:
            raise ValueError('Tên cầu thủ không hợp lệ.')
        rating = int(request.form.get('rating', '80'))
        level = int(request.form.get('level', '0'))
        transfer_value = float(request.form.get('transfer_value', '0'))
        position = request.form.get('position', PLAYER_POSITIONS.get(name, 'ST')).upper()
        card_type = request.form.get('card_type', 'REGULAR').upper()
        card_season = request.form.get('card_season', 'Thường').strip() or 'Thường'
        source_url = request.form.get('metadata_source_url', '').strip()[:500]
        photo_url = request.form.get('photo_url', '').strip()[:500]

        from urllib.parse import urlparse
        if photo_url:
            parsed = urlparse(photo_url)
            if parsed.scheme != 'https' or not parsed.netloc:
                raise ValueError('Ảnh cầu thủ phải dùng đường dẫn HTTPS hợp lệ.')
        if rating < 1 or level < 0 or not math.isfinite(transfer_value) or transfer_value < 0:
            raise ValueError('OVR/cấp thẻ không hợp lệ hoặc giá trị chuyển nhượng bị âm.')
        if position not in {'GK','CB','LB','RB','LWB','RWB','CDM','CM','CAM','LM','RM','LW','RW','ST','CF'}:
            raise ValueError('Vị trí cầu thủ không hợp lệ.')
        if card_type not in {'REGULAR', 'HEROES', 'ICON'}:
            raise ValueError('Phân loại thẻ không hợp lệ.')
        if card_type in {'ICON', 'HEROES'}:
            parsed = urlparse(source_url)
            trusted = ('fifa.com','uefa.com','worldfootball.net','rsssf.org','transfermarkt.com',
                       'premierleague.com','laliga.com','bundesliga.com','ligue1.com','seriea.com',
                       'the-afc.com','conmebol.com','concacaf.com','cafonline.com')
            host = (parsed.hostname or '').lower()
            if parsed.scheme != 'https' or not any(host == domain or host.endswith('.' + domain) for domain in trusted):
                raise ValueError('ICON/HEROES cần nguồn HTTPS từ website bóng đá uy tín.')

        state = load_state(save)
        gifted = {
            'name': name, 'position': position, 'rating': rating, 'level': level,
            'card_season': card_season, 'market_value': transfer_value,
            'nationality': '', 'club': '', 'league': '', 'card_type': card_type,
            'metadata_source_url': source_url, 'metadata_admin_verified': True,
            'metadata_complete': False, 'photo_url': photo_url,
            'is_icon': card_type == 'ICON', 'is_hero': card_type == 'HEROES',
        }
        if card_season.casefold() in {"ballon d’or", "ballon d'or"}:
            gifted['event_card'] = 'ballon_dor'
        elif card_season.casefold() == 'christmas 2026':
            gifted['event_card'] = 'christmas_2026'

        mail = {
            'id': secrets.token_urlsafe(12), 'type': 'player_gift',
            'subject': request.form.get('mail_subject', '').strip()[:100] or 'Bạn nhận được một gói cầu thủ!',
            'body': request.form.get('mail_body', '').strip()[:1000] or 'Admin gửi tặng bạn một cầu thủ. Nhấn Mở để nhận vào đội hình dự bị.',
            'player': gifted, 'opened': False,
            'created_at': datetime.utcnow().strftime('%d/%m/%Y %H:%M')
        }
        state.setdefault('mailbox', []).insert(0, mail)
        state.setdefault('activity', []).insert(0, {
            'message': f'Admin gửi thư tặng {name} OVR {rating} +{level}',
            'week': state.get('week', 1)
        })
        state['activity'] = state['activity'][:15]
        persist(save, state)
        flash(f'Đã gửi gói {name} vào hòm thư của {recipient.username}.')
    except (ValueError, TypeError) as error:
        flash(str(error))
    return redirect(url_for('admin_panel'))


@app.post('/admin/gift-trophy')
@admin_required
def admin_gift_trophy():
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang Admin.')
        return redirect(url_for('admin_panel'))
    try:
        user_id = int(request.form.get('user_id', ''))
        recipient = db.session.get(User, user_id)
        if not recipient or recipient.is_admin:
            raise ValueError('Không tìm thấy tài khoản người chơi hợp lệ.')
        save = GameSave.query.filter_by(user_id=recipient.id).first()
        if not save:
            raise ValueError('Tài khoản này chưa có dữ liệu game.')
        title = request.form.get('trophy_name', '').strip()[:48]
        subtitle = request.form.get('trophy_desc', '').strip()[:100]
        frame = request.form.get('frame_style', 'gold').strip().lower()
        styles = {
            'gold': {'label':'Vàng Hoàng Gia','class':'trophy-gold'},
            'diamond': {'label':'Kim Cương','class':'trophy-diamond'},
            'ruby': {'label':'Hồng Ngọc','class':'trophy-ruby'},
            'amethyst': {'label':'Tím Huyền Bí','class':'trophy-amethyst'},
            'emerald': {'label':'Ngọc Lục Bảo','class':'trophy-emerald'},
            'obsidian': {'label':'Hắc Kim','class':'trophy-obsidian'},
        }
        if not title:
            raise ValueError('Tên danh hiệu không được để trống.')
        if frame not in styles:
            raise ValueError('Kiểu khung danh hiệu không hợp lệ.')
        state = load_state(save)
        trophy = {'id': secrets.token_urlsafe(8), 'name': title, 'description': subtitle,
                  'frame_style': frame, 'frame_class': styles[frame]['class'],
                  'frame_label': styles[frame]['label'],
                  'awarded_at': datetime.utcnow().strftime('%d/%m/%Y')}
        mail = {
            'id': secrets.token_urlsafe(12), 'type': 'trophy_gift',
            'subject': request.form.get('trophy_mail_subject', '').strip()[:100] or 'Bạn nhận được một danh hiệu mới!',
            'body': request.form.get('trophy_mail_body', '').strip()[:1000] or 'Admin gửi tặng bạn một danh hiệu. Nhấn Mở trong Hòm thư để nhận và thêm vào hồ sơ.',
            'trophy': trophy, 'opened': False,
            'created_at': datetime.utcnow().strftime('%d/%m/%Y %H:%M')
        }
        state.setdefault('mailbox', []).insert(0, mail)
        state.setdefault('activity', []).insert(0, {'message': f'Admin gửi thư tặng danh hiệu: {title}', 'week': state.get('week', 1)})
        state['activity'] = state['activity'][:15]
        persist(save, state)
        flash(f'Đã gửi thư danh hiệu “{title}” vào Hòm thư của {recipient.username}.')
    except (ValueError, TypeError) as error:
        flash(str(error))
    return redirect(url_for('admin_panel'))


@app.post('/admin/reset-password')
@admin_required
def admin_reset_password():
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang Admin.')
        return redirect(url_for('admin_panel'))

    try:
        user_id = int(request.form.get('user_id', ''))
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        target = db.session.get(User, user_id)

        if not target:
            raise ValueError('Không tìm thấy tài khoản.')

        if target.is_admin:
            raise ValueError('Không thể đặt lại mật khẩu Admin.')

        if len(new_password) < 8:
            raise ValueError('Mật khẩu mới phải có ít nhất 8 ký tự.')

        if new_password != confirm_password:
            raise ValueError('Mật khẩu xác nhận không khớp.')

        target.set_password(new_password)
        db.session.commit()

        flash(f'Đã đặt lại mật khẩu cho tài khoản {target.username}.')

    except (ValueError, TypeError) as error:
        db.session.rollback()
        flash(str(error))

    return redirect(url_for('admin_panel'))

@app.post('/admin/gift-item')
@admin_required
def admin_gift_item():
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang Admin.')
        return redirect(url_for('admin_panel'))
    try:
        user_id = int(request.form.get('user_id', ''))
        quantity = int(request.form.get('quantity', '0'))
        recipient = db.session.get(User, user_id)
        if not recipient or recipient.is_admin:
            raise ValueError('Tài khoản nhận không hợp lệ.')
        if quantity < 1 or quantity > 100000:
            raise ValueError('Số lượng vật phẩm phải từ 1 đến 100.000.')
        item_name = request.form.get('item_name', '').strip()
        if item_name != 'Thẻ bảo vệ':
            raise ValueError('Vật phẩm không hợp lệ.')
        save = GameSave.query.filter_by(user_id=recipient.id).first()
        if not save:
            raise ValueError('Tài khoản này chưa có dữ liệu game.')
        state = load_state(save)
        inventory = state.setdefault('inventory', {})
        inventory[item_name] = int(inventory.get(item_name, 0)) + quantity
        state.setdefault('activity', []).insert(0, {
            'message': f'Admin tặng {quantity} {item_name}',
            'week': state.get('week', 1)
        })
        state['activity'] = state['activity'][:15]
        persist(save, state)
        flash(f'Đã tặng {quantity} {item_name} cho {recipient.username}.')
    except (ValueError, TypeError) as error:
        db.session.rollback()
        flash(str(error))
    return redirect(url_for('admin_panel'))

@app.route('/mailbox')
@login_required
def mailbox():
    save = current_save()
    if not save:
        return redirect(url_for('choose_club'))
    state = load_state(save)
    mails = state.setdefault('mailbox', [])
    return render_template('mailbox.html', mails=mails, unread_count=sum(1 for m in mails if not m.get('opened')))

@app.post('/mailbox/open')
@login_required
def mailbox_open():
    save = current_save()
    if not save:
        return redirect(url_for('choose_club'))
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang.')
        return redirect(url_for('mailbox'))
    state = load_state(save)
    mail_id = request.form.get('mail_id', '')
    mail = next((m for m in state.setdefault('mailbox', []) if m.get('id') == mail_id), None)
    if not mail:
        flash('Không tìm thấy thư đã chọn.')
    elif mail.get('opened'):
        flash('Thư này đã được mở trước đó.')
    elif mail.get('type') == 'trophy_gift':
        trophy = copy.deepcopy(mail.get('trophy') or {})
        if not trophy.get('name'):
            flash('Danh hiệu trong thư không hợp lệ.')
        else:
            owned = state.setdefault('profile_trophies', [])
            if not any(t.get('id') == trophy.get('id') for t in owned):
                owned.insert(0, trophy)
                state['profile_trophies'] = owned[:30]
            mail['opened'] = True
            state.setdefault('activity', []).insert(0, {'message': f'Đã nhận danh hiệu: {trophy["name"]}', 'week': state.get('week', 1)})
            state['activity'] = state['activity'][:15]
            flash(f'Đã nhận danh hiệu “{trophy["name"]}” vào hồ sơ!')
    elif mail.get('type') == 'player_gift':
        gifted = copy.deepcopy(mail.get('player') or {})
        if gifted.get('rating') is None and gifted.get('ovr') is not None:
            gifted['rating'] = gifted.get('ovr')
        if gifted.get('name') == 'Zidane':
            gifted['name'] = 'Zinedine Zidane'
        if gifted.get('name') == 'Zinedine Zidane':
            gifted.setdefault('position', 'CAM')
            gifted.setdefault('rating', 101)
        gifted.setdefault('level', 0)
        if not gifted.get('name'):
            flash('Gói quà trong thư không hợp lệ.')
        else:
            # Quà mới nhận không bị danh sách cầu thủ từng bán loại bỏ.
            gifted_key = str(gifted['name']).strip().casefold()
            state['market_removed_players'] = [
                n for n in state.get('market_removed_players', [])
                if str(n).strip().casefold() != gifted_key
            ]
            # Mỗi lần nhận là một bản thẻ riêng; trùng tên/mùa vẫn được giữ.
            state.setdefault('bench', []).append(gifted)
            mail['opened'] = True
            state.setdefault('activity', []).insert(0, {'message': f'Đã nhận quà từ hòm thư: {gifted["name"]}', 'week': state.get('week', 1)})
            state['activity'] = state['activity'][:15]
            flash(f'Đã mở thư và nhận {gifted["name"]} vào đội hình dự bị!')
    else:
        flash('Loại thư này chưa được hỗ trợ.')
    persist(save, state)
    return redirect(url_for('mailbox'))

@app.post('/mailbox/claim-all')
@login_required
def mailbox_claim_all():
    save = current_save()
    if not save:
        return redirect(url_for('choose_club'))
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang.')
        return redirect(url_for('mailbox'))
    state = load_state(save)
    received = []
    for mail in state.setdefault('mailbox', []):
        if mail.get('opened'):
            continue
        if mail.get('type') == 'trophy_gift':
            trophy = copy.deepcopy(mail.get('trophy') or {})
            if trophy.get('name'):
                owned = state.setdefault('profile_trophies', [])
                if not any(t.get('id') == trophy.get('id') for t in owned):
                    owned.insert(0, trophy)
                    state['profile_trophies'] = owned[:30]
                mail['opened'] = True
                received.append(f'Danh hiệu: {trophy["name"]}')
            continue
        if mail.get('type') != 'player_gift':
            continue
        gifted = copy.deepcopy(mail.get('player') or {})
        if gifted.get('rating') is None and gifted.get('ovr') is not None:
            gifted['rating'] = gifted.get('ovr')
        if gifted.get('name') == 'Zidane':
            gifted['name'] = 'Zinedine Zidane'
        if gifted.get('name') == 'Zinedine Zidane':
            gifted.setdefault('position', 'CAM')
            gifted.setdefault('rating', 101)
        gifted.setdefault('level', 0)
        if not gifted.get('name'):
            mail['opened'] = True
            continue
        # Quà mới nhận không bị danh sách cầu thủ từng bán loại bỏ.
        gifted_key = str(gifted['name']).strip().casefold()
        state['market_removed_players'] = [
            n for n in state.get('market_removed_players', [])
            if str(n).strip().casefold() != gifted_key
        ]
        # Mỗi thư thêm một bản cầu thủ vào kho, kể cả trùng tên.
        state.setdefault('bench', []).append(gifted)
        mail['opened'] = True
        received.append(gifted['name'])
    if received:
        state.setdefault('activity', []).insert(0, {'message': f'Đã nhận {len(received)} phần quà từ hòm thư', 'week': state.get('week', 1)})
        state['activity'] = state['activity'][:15]
        flash('Đã nhận: ' + ', '.join(received) + '.')
    else:
        flash('Không có gói cầu thủ mới để nhận.')
    persist(save, state)
    return redirect(url_for('mailbox'))

@app.post('/admin/budget')
@admin_required
def admin_budget():
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang Admin.')
        return redirect(url_for('admin_panel'))
    try:
        user_id = int(request.form.get('user_id', ''))
        amount = float(request.form.get('amount', '0'))
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError('Số tiền tặng phải là số hữu hạn lớn hơn 0.')
        save = GameSave.query.filter_by(user_id=user_id).first()
        recipient = db.session.get(User, user_id)
        if not save or not recipient:
            raise ValueError('Không tìm thấy dữ liệu game của tài khoản này.')
        state = load_state(save)
        state['budget'] = round(float(state.get('budget', 0)) + amount, 2)
        state.setdefault('activity', []).insert(0, {'message': f'Admin tặng 🪙 {amount:g}M PC', 'week': state.get('week', 1)})
        state['activity'] = state['activity'][:15]
        persist(save, state)
        flash(f'Đã tặng 🪙 {amount:g}M PC cho tài khoản {recipient.username}.')
    except (ValueError, TypeError) as error:
        flash(str(error))
    return redirect(url_for('admin_panel'))




@app.post('/admin/pg')
@admin_required
def admin_pg():
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang Admin.')
        return redirect(url_for('admin_panel'))
    try:
        user_id = int(request.form.get('user_id', ''))
        amount = int(request.form.get('amount', '0'))
        if amount <= 0 or amount > 1_000_000_000:
            raise ValueError('Số PG phải là số nguyên dương hợp lệ.')
        recipient = db.session.get(User, user_id)
        save = GameSave.query.filter_by(user_id=user_id).first()
        if not recipient or recipient.is_admin or not save:
            raise ValueError('Không tìm thấy tài khoản người chơi hợp lệ.')
        state = load_state(save)
        state['pg_balance'] = int(state.get('pg_balance', 0)) + amount
        state.setdefault('activity', []).insert(0, {'message': f'Admin tặng 💎 {amount:,} PG', 'week': state.get('week', 1)})
        state['activity'] = state['activity'][:15]
        persist(save, state)
        flash(f'Đã tặng {amount:,} PG cho tài khoản {recipient.username}.')
    except (ValueError, TypeError) as error:
        db.session.rollback()
        flash(str(error))
    return redirect(url_for('admin_panel'))

@app.post('/profile/trophies-visibility')
@login_required
def profile_trophies_visibility():
    save = current_save()
    if not save:
        return redirect(url_for('choose_club'))
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang.')
        return redirect(url_for('dashboard'))
    state = load_state(save)
    selected_ids = set(request.form.getlist('visible_trophy_ids'))
    trophies = state.setdefault('profile_trophies', [])
    for trophy in trophies:
        # Old trophies default to visible until the player changes their selection.
        trophy['visible'] = str(trophy.get('id')) in selected_ids
    state['profile_trophies_visible'] = True
    persist(save, state)
    visible_count = sum(1 for trophy in trophies if trophy.get('visible', True))
    flash(f'Đã lưu lựa chọn hiển thị: {visible_count}/{len(trophies)} danh hiệu. Danh hiệu bị ẩn vẫn được giữ trong kho.')
    return redirect(url_for('dashboard'))


def friend_pair(a, b):
    return (min(a, b), max(a, b))

def are_friends(a, b):
    low, high = friend_pair(a, b)
    return Friendship.query.filter_by(user_low_id=low, user_high_id=high).first() is not None

def get_user_profile(user):
    save = GameSave.query.filter_by(user_id=user.id).first()
    state = load_state(save) if save else {}
    history = (state.get('match_history') or [])[:5]
    wins = sum(1 for m in history if m.get('result') == 'Thắng')
    draws = sum(1 for m in history if m.get('result') == 'Hòa')
    losses = sum(1 for m in history if m.get('result') == 'Thua')
    dashboard_data = get_dashboard(state) if state else {}
    ovr_average = float(dashboard_data.get('average_rating', 0) or 0)
    online = bool(user.last_seen_at and user.last_seen_at >= datetime.utcnow() - timedelta(seconds=90))
    return {'user': user, 'state': state, 'history': history, 'wins': wins, 'draws': draws, 'losses': losses,
            'club_name': state.get('custom_club_name') or state.get('club', 'Chưa chọn'),
            'matches': int(state.get('wins', 0) or 0)+int(state.get('draws', 0) or 0)+int(state.get('losses', 0) or 0),
            'win_rate': round(100*int(state.get('wins', 0) or 0)/max(1,int(state.get('wins', 0) or 0)+int(state.get('draws', 0) or 0)+int(state.get('losses', 0) or 0)),1),
            'ovr': ovr_average, 'online': online, 'squad_value': float(dashboard_data.get('squad_value', 0) or 0), 'trophies': [t for t in state.get('profile_trophies', []) if t.get('visible', True)] if state.get('profile_trophies_visible', True) else [], 'trophies_visible': state.get('profile_trophies_visible', True)}

@app.before_request
def update_presence():
    if current_user.is_authenticated and request.endpoint not in {'static', 'presence_ping'}:
        current_user.last_seen_at = datetime.utcnow()
        db.session.commit()

@app.post('/presence/ping')
@login_required
def presence_ping():
    current_user.last_seen_at = datetime.utcnow()
    db.session.commit()
    return {'ok': True}

@app.get('/friends/presence')
@login_required
def friends_presence():
    links = Friendship.query.filter((Friendship.user_low_id == current_user.id) | (Friendship.user_high_id == current_user.id)).all()
    ids = [f.user_high_id if f.user_low_id == current_user.id else f.user_low_id for f in links]
    cutoff = datetime.utcnow() - timedelta(seconds=90)
    online_ids = [u.id for u in User.query.filter(User.id.in_(ids), User.last_seen_at >= cutoff).all()] if ids else []
    return jsonify({'online_ids': online_ids})

@app.route('/friends', methods=['GET', 'POST'])
@login_required
def friends():
    if current_user.is_admin:
        return redirect(url_for('admin_panel'))
    save = current_save()
    if not save:
        return redirect(url_for('choose_club'))
    query = request.args.get('q', '').strip()[:32]
    results = []
    if query:
        results = User.query.filter(User.username.ilike(f'%{query}%'), User.id != current_user.id, User.is_admin.is_(False)).order_by(User.username.asc()).limit(20).all()
    lows = Friendship.query.filter((Friendship.user_low_id == current_user.id) | (Friendship.user_high_id == current_user.id)).all()
    friend_ids = [f.user_high_id if f.user_low_id == current_user.id else f.user_low_id for f in lows]
    friend_users = User.query.filter(User.id.in_(friend_ids)).order_by(User.username.asc()).all() if friend_ids else []
    friend_profiles = [get_user_profile(u) for u in friend_users]
    incoming = FriendRequest.query.filter_by(receiver_id=current_user.id, status='pending').all()
    outgoing = FriendRequest.query.filter_by(sender_id=current_user.id, status='pending').all()
    incoming_items = [(r, db.session.get(User, r.sender_id)) for r in incoming]
    outgoing_items = [(r, db.session.get(User, r.receiver_id)) for r in outgoing]
    challenges = FriendlyChallenge.query.filter(
        ((FriendlyChallenge.receiver_id == current_user.id) | (FriendlyChallenge.sender_id == current_user.id)),
        FriendlyChallenge.status == 'pending').order_by(FriendlyChallenge.created_at.desc()).all()
    challenge_items = [(c, db.session.get(User, c.sender_id), db.session.get(User, c.receiver_id)) for c in challenges]
    return render_template('friends.html', query=query, results=results, friend_profiles=friend_profiles,
                           incoming_items=incoming_items, outgoing_items=outgoing_items, challenge_items=challenge_items)

@app.get('/friends/profile/<int:user_id>')
@login_required
def friend_profile(user_id):
    if current_user.is_admin:
        return redirect(url_for('admin_panel'))
    target = db.session.get(User, user_id)
    if not target or not are_friends(current_user.id, target.id):
        flash('Chỉ có thể xem hồ sơ của bạn bè.')
        return redirect(url_for('friends'))
    profile = get_user_profile(target)
    state = profile['state']
    # Friend profile is read-only and intentionally shows only the starting XI.
    squad = (state.get('starting', []) or [])[:11]
    return render_template('friend_profile.html', profile=profile, squad=squad)

@app.post('/friends/request/<int:user_id>')
@login_required
def friend_request_send(user_id):
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang.')
        return redirect(url_for('friends'))
    target = db.session.get(User, user_id)
    if not target or target.id == current_user.id or target.is_admin:
        flash('Không thể gửi lời mời kết bạn tới tài khoản này.')
    elif are_friends(current_user.id, target.id):
        flash('Hai người đã là bạn bè.')
    elif FriendRequest.query.filter_by(sender_id=current_user.id, receiver_id=target.id, status='pending').first():
        flash('Bạn đã gửi lời mời cho người này rồi.')
    else:
        reverse = FriendRequest.query.filter_by(sender_id=target.id, receiver_id=current_user.id, status='pending').first()
        if reverse:
            low, high = friend_pair(current_user.id, target.id)
            db.session.add(Friendship(user_low_id=low, user_high_id=high))
            reverse.status = 'accepted'
            db.session.commit()
            flash(f'Bạn và {target.username} đã trở thành bạn bè!')
        else:
            old_request = FriendRequest.query.filter_by(sender_id=current_user.id, receiver_id=target.id).first()
            if old_request:
                old_request.status = 'pending'
                old_request.created_at = datetime.utcnow()
            else:
                db.session.add(FriendRequest(sender_id=current_user.id, receiver_id=target.id))
            db.session.commit()
            flash('Đã gửi lời mời kết bạn.')
    return redirect(url_for('friends'))

@app.post('/friends/request/<int:request_id>/<decision>')
@login_required
def friend_request_decide(request_id, decision):
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang.')
        return redirect(url_for('friends'))
    item = db.session.get(FriendRequest, request_id)
    if not item or item.receiver_id != current_user.id or item.status != 'pending' or decision not in {'accept','decline'}:
        flash('Lời mời không hợp lệ hoặc đã được xử lý.')
    elif decision == 'accept':
        low, high = friend_pair(item.sender_id, item.receiver_id)
        if not are_friends(item.sender_id, item.receiver_id):
            db.session.add(Friendship(user_low_id=low, user_high_id=high))
        item.status = 'accepted'
        db.session.commit()
        flash('Đã chấp nhận lời mời kết bạn!')
    else:
        item.status = 'declined'; db.session.commit(); flash('Đã từ chối lời mời.')
    return redirect(url_for('friends'))

@app.post('/friends/challenge/<int:user_id>')
@login_required
def friendly_challenge_send(user_id):
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang.')
        return redirect(url_for('friends'))
    target = db.session.get(User, user_id)
    if not target or target.id == current_user.id or not are_friends(current_user.id, user_id):
        flash('Chỉ có thể mời bạn bè đá giao hữu.')
    elif not GameSave.query.filter_by(user_id=user_id).first():
        flash('Bạn này chưa có đội bóng để đá giao hữu.')
    elif FriendlyChallenge.query.filter_by(sender_id=current_user.id, receiver_id=user_id, status='pending').first():
        flash('Bạn đã gửi lời mời giao hữu đang chờ phản hồi.')
    else:
        db.session.add(FriendlyChallenge(sender_id=current_user.id, receiver_id=user_id))
        db.session.commit(); flash(f'Đã gửi lời mời giao hữu tới {target.username}.')
    return redirect(url_for('friends'))

def resolve_friendly_match(challenge):
    a = GameSave.query.filter_by(user_id=challenge.sender_id).first()
    b = GameSave.query.filter_by(user_id=challenge.receiver_id).first()
    if not a or not b:
        raise ValueError('Một trong hai đội bóng không còn tồn tại.')
    sa, sb = load_state(a), load_state(b)
    def team_ovr(st):
        vals = [float(p.get('rating', 0)) + float(p.get('level', 0)) for p in st.get('starting', [])]
        return sum(vals)/len(vals) if vals else 60
    oa, ob = team_ovr(sa), team_ovr(sb)
    def goals(attack, defence):
        lam = max(.15, min(3.8, 1.25 + (attack-defence)*.055))
        prob = math.exp(-lam); cumulative = prob; r = random.random(); k = 0
        while r > cumulative and k < 7:
            k += 1; prob *= lam/k; cumulative += prob
        return k
    ga, gb = goals(oa, ob), goals(ob, oa)
    now = datetime.utcnow().strftime('%d/%m/%Y %H:%M')
    ida, idb = db.session.get(User, challenge.sender_id), db.session.get(User, challenge.receiver_id)
    if not ida or not idb:
        raise ValueError('Không tìm thấy tài khoản tham gia giao hữu.')
    home_club, away_club = sa.get('club','CLB'), sb.get('club','CLB')
    result = {'home_user': ida.username, 'away_user': idb.username, 'home_club': home_club, 'away_club': away_club,
              'score': f'{ga} - {gb}', 'home_ovr': round(oa,1), 'away_ovr': round(ob,1), 'played_at': now, 'friendly': True}

    events, used = [], set()
    def event_minute():
        choices = [m for m in range(1, 91) if m not in used]
        if not choices: return 90
        value = random.choice(choices); used.add(value); return value
    for team_name, squad, count in [(home_club, sa.get('starting', []), ga), (away_club, sb.get('starting', []), gb)]:
        scorers = [p for p in squad if str(p.get('position','')).upper() != 'GK'] or squad
        for _ in range(count):
            if scorers:
                scorer = random.choice(scorers)
                events.append({'minute':event_minute(), 'type':'goal', 'team':team_name,
                               'player':scorer.get('name','Cầu thủ'), 'detail':'Bàn thắng'})
        if squad and random.random() < .45:
            card = random.choice(squad)
            events.append({'minute':event_minute(), 'type':'card', 'team':team_name,
                           'player':card.get('name','Cầu thủ'), 'detail':'Thẻ vàng 🟨'})
        if squad and random.random() < .06:
            card = random.choice(squad)
            events.append({'minute':event_minute(), 'type':'card', 'team':team_name,
                           'player':card.get('name','Cầu thủ'), 'detail':'Thẻ đỏ 🟥'})
    events.sort(key=lambda e:e['minute'])
    yellow = sum(1 for e in events if e['type']=='card' and 'vàng' in e['detail'])
    red = sum(1 for e in events if e['type']=='card' and 'đỏ' in e['detail'])
    for st, club, opponent, gf, gc, own_ovr, opp_ovr in [
        (sa, home_club, away_club, ga, gb, oa, ob),
        (sb, away_club, home_club, gb, ga, ob, oa)
    ]:
        label = 'Thắng' if gf > gc else ('Hòa' if gf == gc else 'Thua')
        match_stats = {'goals_home':gf, 'goals_away':gc, 'penalties':0, 'own_goals':0,
                       'yellow_cards':yellow, 'red_cards':red}
        st.setdefault('match_history', []).insert(0, {
            'id':secrets.token_urlsafe(8), 'club':club, 'opponent':opponent,
            'score':f'{gf} - {gc}', 'result':label, 'reward':0,
            'my_ovr':round(own_ovr,1), 'opponent_ovr':round(opp_ovr,1),
            'friendly':True, 'played_at':now, 'events':copy.deepcopy(events), 'stats':match_stats
        })
        st['match_history'] = st['match_history'][:5]
        st.setdefault('activity', []).insert(0, {'message':f'Giao hữu với {opponent}: {gf} - {gc}', 'week':st.get('week',1)})
        st['activity'] = st['activity'][:15]
    persist(a, sa); persist(b, sb)
    challenge.result_json = result; challenge.status = 'completed'
    db.session.commit()
    return result

@app.post('/friends/challenge/<int:challenge_id>/<decision>')
@login_required
def friendly_challenge_decide(challenge_id, decision):
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang.')
        return redirect(url_for('friends'))
    challenge = db.session.get(FriendlyChallenge, challenge_id)
    if not challenge or challenge.receiver_id != current_user.id or challenge.status != 'pending' or decision not in {'accept','decline'}:
        flash('Lời mời giao hữu không hợp lệ hoặc đã xử lý.')
    elif decision == 'decline':
        challenge.status = 'declined'; db.session.commit(); flash('Đã từ chối lời mời giao hữu.')
    else:
        try:
            result = resolve_friendly_match(challenge)
            flash(f"Giao hữu kết thúc: {result['home_club']} {result['score']} {result['away_club']}! Kết quả đã lưu vào hồ sơ cả hai đội.")
        except ValueError as error:
            db.session.rollback(); flash(str(error))
    return redirect(url_for('friends'))

@app.post('/action')
@login_required
def action():
    save=GameSave.query.filter_by(user_id=current_user.id).with_for_update().first()
    if not save: return redirect(url_for('choose_club'))
    st=load_state(save); ensure_daily_quests(st); act=request.form.get('action'); result=None
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    upgrade_response = None
    quest_event=None; quest_data={}
    try:
        if act=='swap':
            a=int(request.form['a']); b=int(request.form['b'])
            if a < 0 or a >= len(st['starting']) or b < 0 or b >= len(st['bench']):
                raise ValueError('Không tìm thấy cầu thủ cần thay.')
            out=st['starting'][a]; inn=st['bench'][b]
            out_position = str(out.get('assigned_position') or out.get('position', '')).strip().upper()
            in_position = str(inn.get('position', '')).strip().upper()
            if (out_position == 'GK') != (in_position == 'GK'):
                raise ValueError('Thủ môn chỉ có thể thay thế thủ môn. Các vị trí ngoài sân có thể thay thế cho nhau.')
            inn['assigned_position'] = out_position
            out['assigned_position'] = str(out.get('position', out_position)).upper()
            duplicate = any(p['name'].strip().casefold() == inn['name'].strip().casefold() for i,p in enumerate(st['starting']) if i != a)
            if duplicate: raise ValueError(f"Không thể thay: {inn['name']} đã có trong đội hình đá chính.")
            st['starting'][a],st['bench'][b]=inn,out; flash(f"Đã thay {out['name']} bằng {inn['name']}.")
        elif act=='drag_swap':
            source_group=request.form.get('source_group',''); source_index=int(request.form.get('source_index','-1'))
            target_index=int(request.form.get('target_index','-1')); target_group=request.form.get('target_group','starting')
            if source_group not in {'starting','bench'} or target_group not in {'starting','bench'}: raise ValueError('Danh sách kéo thả không hợp lệ.')
            source=st[source_group]
            if source_index<0 or source_index>=len(source): raise ValueError('Không tìm thấy cầu thủ được kéo.')
            incoming=source[source_index]
            if target_group=='bench':
                if source_group!='starting' or target_index!=-1: raise ValueError('Chỉ kéo cầu thủ đá chính xuống khu vực dự bị.')
                if str(incoming.get('assigned_position') or incoming.get('position','')).upper()=='GK' and not any(str(x.get('position','')).upper()=='GK' for x in st['bench']): raise ValueError('Cần có thủ môn dự bị trước khi đưa thủ môn ra ngoài.')
                st['bench'].append(incoming); st['starting'].pop(source_index)
            else:
                if target_index<0 or target_index>=len(st['starting']): raise ValueError('Vị trí đích không hợp lệ.')
                outgoing=st['starting'][target_index]
                incoming_pos=str(incoming.get('position','')).upper(); target_pos=str(outgoing.get('assigned_position') or outgoing.get('position','')).upper()
                if (incoming_pos=='GK') != (target_pos=='GK'): raise ValueError('Thủ môn chỉ có thể thay thế thủ môn.')
                if source_group == 'bench' and any(
                    str(p.get('name', '')).strip().casefold() == str(incoming.get('name', '')).strip().casefold()
                    for i, p in enumerate(st['starting']) if i != target_index
                ):
                    raise ValueError(f"Không thể xếp {incoming.get('name')} vì cầu thủ này đã có trong đội hình đá chính.")
                if source_group=='bench': st['starting'][target_index],st['bench'][source_index]=incoming,outgoing
                else: st['starting'][target_index],st['starting'][source_index]=incoming,outgoing
                st['starting'][target_index]['assigned_position']=target_pos
                if source_group=='starting': st['starting'][source_index]['assigned_position']=str(st['starting'][source_index].get('position','')).upper()
        elif act=='promote':
            group=request.form.get('group')
            idx=int(request.form.get('index','-1'))
            if group not in {'bench','extras'}:
                raise ValueError('Danh sách cầu thủ không hợp lệ.')
            if len(st['starting']) >= 11:
                raise ValueError('Đội hình đá chính đã đủ 11 cầu thủ.')

            reserve=st[group]
            if idx < 0 or idx >= len(reserve):
                raise ValueError('Không tìm thấy cầu thủ dự bị.')

            incoming=reserve[idx]
            incoming_pos=str(incoming.get('position','')).strip().upper()
            has_starting_gk=any(
                str(p.get('position','')).strip().upper() == 'GK'
                or str(p.get('assigned_position','')).strip().upper() == 'GK'
                for p in st['starting']
            )

            # Thủ môn chỉ được bổ sung khi đội hình đang thiếu GK.
            # Khi đã có GK, chỉ cho bổ sung cầu thủ ngoài sân vào chỗ còn thiếu.
            if not has_starting_gk and incoming_pos != 'GK':
                raise ValueError('Đội hình đang thiếu thủ môn. Chỉ có thể thêm một cầu thủ GK.')
            if has_starting_gk and incoming_pos == 'GK':
                raise ValueError('Đội hình đã có thủ môn. Chỉ có thể thêm cầu thủ ngoài sân.')

            if any(
                str(p.get('name','')).strip().casefold()
                == str(incoming.get('name','')).strip().casefold()
                for p in st['starting']
            ):
                raise ValueError(f"Không thể thêm: {incoming['name']} đã có trong đội hình đá chính.")

            promoted=reserve.pop(idx)
            # Giữ GK ở cuối danh sách để khớp vị trí thủ môn trên sân.
            if incoming_pos == 'GK':
                st['starting'].append(promoted)
            else:
                keeper=next(
                    (p for p in st['starting']
                     if str(p.get('position','')).strip().upper() == 'GK'
                     or str(p.get('assigned_position','')).strip().upper() == 'GK'),
                    None
                )
                if keeper:
                    st['starting'].remove(keeper)
                    st['starting'].append(promoted)
                    st['starting'].append(keeper)
                else:
                    st['starting'].append(promoted)

            flash(f"Đã thêm {incoming['name']} vào đội hình đá chính. Hiện có {len(st['starting'])}/11 cầu thủ.")
        elif act=='buy':
            name=request.form.get('name','').strip()
            if name not in st['market'] or name in PACKS['4']['players']: raise ValueError('Cầu thủ không có trên TTCN thông thường.')
            cost=float(PLAYER_PRICES.get(name,0))
            if cost <= 0: raise ValueError('Giá cầu thủ không hợp lệ.')
            if st['budget'] + 1e-9 < cost: raise ValueError(f'Không đủ ngân sách. Cần 🪙 {cost:g}M PC, hiện có 🪙 {st["budget"]:g}M PC.')
            st['budget']=round(st['budget']-cost,2); st['bench'].append(player(name))
            quest_event='buy'; quest_data={'pc_spent': cost}
            flash(f'Chiêu mộ thành công {name}. Đã trừ {format_money(cost)}. Ngân sách còn {format_money(st["budget"])}.')
        elif act=='sell':
            group=request.form.get('group'); idx=int(request.form['index'])
            if group not in {'bench','extras'}: raise ValueError('Không thể bán cầu thủ ở danh sách này.')
            arr=st[group]; p=arr[idx]; amount=float(value(p))
            arr.pop(idx); st['budget']=round(st['budget']+amount,2)
            quest_event='sell'; quest_data={'sale_value': amount}
            if p['name'] not in st['market'] and p['name'] not in PACKS['4']['players']: st['market'].append(p['name'])
            flash(f'Đã bán {p["name"]}, cộng {format_money(amount)}. Ngân sách: {format_money(st["budget"])}.')

        elif act=='sell_bulk':
            selected=request.form.getlist('sell_player')
            if not selected: raise ValueError('Hãy chọn ít nhất một cầu thủ để bán.')
            parsed=[]; seen=set()
            for token in selected:
                group, raw_idx=token.split(':',1); idx=int(raw_idx)
                if group not in {'bench','extras'} or idx<0 or idx>=len(st.get(group,[])):
                    raise ValueError('Danh sách cầu thủ được chọn không hợp lệ. Hãy tải lại trang.')
                if (group,idx) in seen: continue
                seen.add((group,idx)); parsed.append((group,idx,st[group][idx]))
            total=0.0; sold_names=[]
            for group,idx,p in parsed:
                amount=float(value(p)); total+=amount; sold_names.append(p.get('name','Cầu thủ'))
                if p['name'] not in st['market'] and p['name'] not in PACKS['4']['players']:
                    st['market'].append(p['name'])
            for group in ('bench','extras'):
                for idx in sorted((i for g,i,_ in parsed if g==group),reverse=True):
                    st[group].pop(idx)
            st['budget']=round(float(st['budget'])+total,2)
            quest_event='sell'; quest_data={'sale_value': total}
            flash(f'Đã bán {len(parsed)} cầu thủ, cộng {format_money(total)} vào ngân sách.')

        elif act=='ballon_pack':
            # Server-side one-time token prevents a browser double-submit from charging twice.
            request_id = request.form.get('request_id', '').strip()
            if not request_id or len(request_id) > 100:
                raise ValueError('Yêu cầu mở gói không hợp lệ. Hãy tải lại trang.')
            processed = st.setdefault('processed_ballon_requests', [])
            if request_id in processed:
                persist(save, st)
                return redirect(url_for('game_tab', tab='shop'))
            cost_pg = 2000
            if int(st.get('pg_balance', 0)) < cost_pg:
                raise ValueError(f'Không đủ PG. Ballon D’or Pack giá {cost_pg:,} PG; bạn hiện có {int(st.get("pg_balance", 0)):,} PG.')
            pool_a = [
                ('Lionel Messi','RW',102,8), ('C. Ronaldo','LW',102,8),
                ('Zinedine Zidane','CAM',101,14), ('Franz Beckenbauer','CB',101,14),
                ('Ronaldo Nazário','ST',101,14), ('Ruud Gullit','CM',101,14),
                ('Lothar Matthäus','CDM',101,14), ('Lev Yashin','GK',101,14)
            ]
            pool_b = [
                ('Neymar Junior','LW',100,2.4), ('R. Lewandowski','ST',100,2.4),
                ('Van Dijk','CB',99,4), ('Paolo Maldini','CB',100,2.4),
                ('Kylian Mbappe','ST',99,4), ('Sadio Mané','LW',99,4),
                ('Gareth Bale','RW',98,8), ('Mohamed Salah','RW',98,8),
                ('Baresi','CB',99,4), ('Xavi','CM',99,4), ('David Beckham','CM',99,4),
                ('Toni Kroos','CAM',98,8), ('KDB','CAM',99,4),
                ('Frank Rijkaard','CDM',100,2.4), ("N'Golo Kanté",'CDM',98,8),
                ('G. Buffon','GK',100,2.4), ('M. Neuer','GK',99,4),
                ('Achraf Hakimi','RB',98,8), ('Philipp Lahm','RB',99,4),
                ('Roberto Carlos','LB',99,4), ('Nuno Mendes','LB',98,8)
            ]
            selected_pool = 'A' if random.random() < .20 else 'B'
            pool = pool_a if selected_pool == 'A' else pool_b
            names, weights = zip(*[(x, x[3]) for x in pool])
            name, position, rating, _weight = random.choices(names, weights=weights, k=1)[0]
            awarded = {'name': name, 'position': position, 'rating': rating, 'level': 0,
                       'event_card': 'ballon_dor', 'original_rating': rating,
                       'card_season': 'Ballon D’or',
                       'market_value': BALLON_DOR_VALUES[name]}
            st['pg_balance'] = int(st.get('pg_balance', 0)) - cost_pg
            st.setdefault('bench', []).append(awarded)
            quest_event='pack'; quest_data={'pg_spent': cost_pg, 'rating': rating}
            processed.append(request_id)
            st['processed_ballon_requests'] = processed[-100:]
            flags = {
                'Lionel Messi':'🇦🇷','C. Ronaldo':'🇵🇹','Zinedine Zidane':'🇫🇷',
                'Franz Beckenbauer':'🇩🇪','Ronaldo Nazário':'🇧🇷','Ruud Gullit':'🇳🇱',
                'Lothar Matthäus':'🇩🇪','Lev Yashin':'🇷🇺','Neymar Junior':'🇧🇷',
                'R. Lewandowski':'🇵🇱','Van Dijk':'🇳🇱','Paolo Maldini':'🇮🇹',
                'Kylian Mbappe':'🇫🇷','Sadio Mané':'🇸🇳','Gareth Bale':'🇬🇧',
                'Mohamed Salah':'🇪🇬','Baresi':'🇮🇹','Xavi':'🇪🇸',
                'David Beckham':'🇬🇧','Toni Kroos':'🇩🇪','KDB':'🇧🇪',
                'Frank Rijkaard':'🇳🇱',"N'Golo Kanté":'🇫🇷','G. Buffon':'🇮🇹',
                'M. Neuer':'🇩🇪','Achraf Hakimi':'🇲🇦','Philipp Lahm':'🇩🇪',
                'Roberto Carlos':'🇧🇷','Nuno Mendes':'🇵🇹'
            }
            st['ballon_reveal'] = {
                'id': request_id, 'name': name, 'position': position, 'rating': rating,
                'pool': selected_pool, 'country_flag': flags.get(name, '🌍')
            }
            st.setdefault('activity', []).insert(0, {
                'message': f'Mở Ballon D’or Pack: nhận {name} OVR {rating} (-2.000 PG)',
                'week': st.get('week', 1)
            })
            # Không flash thông báo kết quả: phần thưởng chỉ được công bố qua màn reveal Ballon D'or.

        elif act=='christmas_pack':
            request_id = request.form.get('request_id', '').strip()
            if not request_id or len(request_id) > 100:
                raise ValueError('Yêu cầu mở gói không hợp lệ. Hãy tải lại trang.')
            processed = st.setdefault('processed_christmas_requests', [])
            if request_id in processed:
                persist(save, st)
                return redirect(url_for('game_tab', tab='shop'))
            cost_pg = 1500
            if int(st.get('pg_balance', 0)) < cost_pg:
                raise ValueError(f'Không đủ PG. Christmas 2026 Pack giá {cost_pg:,} PG; bạn hiện có {int(st.get("pg_balance", 0)):,} PG.')
            # Weights 2/4/6/8 are normalized by random.choices over the total weight 100.
            name, position, rating, _weight, base_value, country_flag = random.choices(
                CHRISTMAS_2026_PLAYERS,
                weights=[entry[3] for entry in CHRISTMAS_2026_PLAYERS],
                k=1
            )[0]
            awarded = {
                'name': name, 'position': position, 'rating': rating, 'level': 0,
                'event_card': 'christmas_2026', 'original_rating': rating,
                'card_season': 'Christmas 2026', 'market_value': base_value,
                'country_flag': country_flag
            }
            st['pg_balance'] = int(st.get('pg_balance', 0)) - cost_pg
            st.setdefault('bench', []).append(awarded)
            quest_event='pack'; quest_data={'pg_spent': cost_pg, 'rating': rating}
            processed.append(request_id)
            st['processed_christmas_requests'] = processed[-100:]
            st['ballon_reveal'] = {
                'id': request_id, 'name': name, 'position': position, 'rating': rating,
                'pool': 'Christmas 2026', 'country_flag': country_flag,
                'event_type': 'christmas_2026', 'season_label': 'CHRISTMAS 2026'
            }
            st.setdefault('activity', []).insert(0, {
                'message': f'Mở Christmas 2026 Pack: nhận {name} OVR {rating} (-1.500 PG)',
                'week': st.get('week', 1)
            })

        elif act=='sweet_candy_pack':
            request_id = request.form.get('request_id', '').strip()
            if not request_id or len(request_id) > 100:
                raise ValueError('Yêu cầu mở gói không hợp lệ. Hãy tải lại trang.')
            processed = st.setdefault('processed_sweet_candy_requests', [])
            if request_id in processed:
                persist(save, st)
                return redirect(url_for('game_tab', tab='shop'))
            cost_pg = 2500
            if int(st.get('pg_balance', 0)) < cost_pg:
                raise ValueError(f'Sweet Candy Pack giá {cost_pg:,} PG; bạn hiện có {int(st.get("pg_balance", 0)):,} PG.')
            name, position, rating, chance, base_value, country_flag = random.choices(
                SWEET_CANDY_PLAYERS, weights=[entry[3] for entry in SWEET_CANDY_PLAYERS], k=1
            )[0]
            awarded = {
                'name': name, 'position': position, 'rating': rating, 'level': 0,
                'event_card': 'sweet_candy', 'original_rating': rating,
                'card_season': 'Sweet Candy', 'market_value': base_value,
                'country_flag': country_flag
            }
            st['pg_balance'] = int(st.get('pg_balance', 0)) - cost_pg
            st.setdefault('bench', []).append(awarded)
            quest_event='pack'; quest_data={'pg_spent': cost_pg, 'rating': rating}
            processed.append(request_id)
            st['processed_sweet_candy_requests'] = processed[-100:]
            st['ballon_reveal'] = {
                'id': request_id, 'name': name, 'position': position, 'rating': rating,
                'pool': 'Sweet Candy', 'country_flag': country_flag,
                'event_type': 'sweet_candy', 'season_label': 'SWEET CANDY'
            }
            st.setdefault('activity', []).insert(0, {
                'message': f'Mở Sweet Candy Pack: nhận {name} OVR {rating} (-2.500 PG)',
                'week': st.get('week', 1)
            })

        elif act=='pack':
            key=request.form.get('pack')
            if key not in PACKS: raise ValueError('Gói cầu thủ không hợp lệ.')
            pack=PACKS[key]; cost=float(pack['price'])
            if st['budget'] + 1e-9 < cost: raise ValueError(f'Không đủ ngân sách. Gói giá 🪙 {cost:g}M PC, bạn hiện có 🪙 {st["budget"]:g}M PC.')
            p=random.choice(pack['players'])
            st['budget']=round(st['budget']-cost,2); st['bench'].append(player(p))
            quest_event='pack'; quest_data={'pc_spent': cost, 'rating': PLAYER_RATINGS.get(p, 80)}
            flash(f'Mở {pack["name"]}: nhận được {p}! Đã trừ {format_money(cost)}, còn {format_money(st["budget"])}.')
        elif act=='upgrade':
            group = request.form.get('group')
            idx = int(request.form.get('index', '-1'))
            if group not in {'starting', 'bench', 'extras'}:
                raise ValueError('Danh sách cầu thủ không hợp lệ.')
            if idx < 0 or idx >= len(st[group]):
                raise ValueError('Không tìm thấy cầu thủ cần ép thẻ.')
            p = st[group][idx]
            level = int(p.get('level', 0))
            if level < 0 or level >= MAX_UPGRADE_LEVEL:
                raise ValueError('Cầu thủ đã đạt cấp ép tối đa +8 hoặc dữ liệu cấp thẻ không hợp lệ.')

            target = level + 1
            cost = upgrade_cost(p, target)
            if st['budget'] + 1e-9 < cost:
                raise ValueError(f'Không đủ ngân sách ép thẻ. Cần {format_money(cost)}.')

            protection_requested = request.form.get('protection') in {'1', 'on', 'true', 'yes'}
            inventory = st.setdefault('inventory', {})
            protection_count = int(inventory.get('Thẻ bảo vệ', 0) or 0)
            if protection_requested and level != 7:
                raise ValueError('Thẻ bảo vệ chỉ dùng khi ép từ +7 lên +8.')
            if protection_requested and protection_count < 1:
                raise ValueError('Bạn không có Thẻ bảo vệ.')

            old_level = level
            st['budget'] = round(st['budget'] - cost, 2)
            if protection_requested:
                inventory['Thẻ bảo vệ'] = protection_count - 1

            success = random.randint(1, 100) <= UPGRADE_RATES[level]
            if success:
                new_level = target
            elif protection_requested:
                new_level = 7
            else:
                distribution = UPGRADE_FAILURE_DISTRIBUTION[level]
                new_level = random.choices(
                    population=list(distribution.keys()),
                    weights=list(distribution.values()),
                    k=1
                )[0]

            p['level'] = new_level
            quest_event='upgrade'; quest_data={'old_level': old_level, 'new_level': new_level, 'success': bool(success), 'pc_spent': cost}
            event = {
                'player': p.get('name', 'Unknown'),
                'from_level': old_level,
                'target_level': target,
                'result_level': new_level,
                'success': bool(success),
                'protected': bool(protection_requested),
                'cost': cost,
                'week': st.get('week', 1),
                'created_at': datetime.utcnow().strftime('%d/%m/%Y %H:%M:%S'),
            }
            p.setdefault('upgrade_history', []).insert(0, copy.deepcopy(event))
            p['upgrade_history'] = p['upgrade_history'][:50]
            st.setdefault('upgrade_history', []).insert(0, event)
            st['upgrade_history'] = st['upgrade_history'][:200]

            player_events = [x for x in st['upgrade_history'] if x.get('player') == p.get('name')]
            total_attempts = len(player_events)
            total_successes = sum(1 for x in player_events if x.get('success'))
            total_spent = sum(float(x.get('cost', 0)) for x in player_events)
            st['last_upgrade_summary'] = {
                'player': p.get('name'), 'attempts': total_attempts,
                'successes': total_successes, 'spent': round(total_spent, 2)
            }
            ovr_bonus = [0,1,2,3,4,6,8,10,13][new_level]
            upgrade_response = {
                'success': bool(success), 'protected': bool(protection_requested),
                'player_name': p.get('name', 'Unknown'), 'group': group, 'index': idx,
                'old_level': old_level, 'target_level': target, 'new_level': new_level,
                'ovr': int(p.get('rating', 0)) + ovr_bonus,
                'base_rating': int(p.get('rating', 0)),
                'base_value': float(p.get('market_value', 0) or 0),
                'value': round(float(p.get('market_value', 0) or 0) * [1.0,1.50,2.25,3.20,4.10,6.35,9.00,12.50,21.00][new_level], 2),
                'budget': st.get('budget', 0),
                'protection_count': int(inventory.get('Thẻ bảo vệ', 0) or 0),
                'cost': cost, 'rate': UPGRADE_RATES[level],
                'message': ('ÉP THẺ THÀNH CÔNG!' if success else ('THẤT BẠI · ĐÃ BẢO VỆ THẺ!' if protection_requested else 'ÉP THẺ THẤT BẠI!'))
            }
        elif act=='match':
            result=simulate_match(st)
            my_goals = int(result.get('score_home', 0)); conceded = int(result.get('score_away', 0))
            scorers = [e.get('player') for e in result.get('events', []) if e.get('type') == 'goal' and e.get('team') == st.get('club') and e.get('player') and 'OG' not in str(e.get('detail', ''))]
            quest_event='match'; quest_data={'won': result.get('result') == 'THẮNG', 'goals': my_goals, 'conceded': conceded, 'goal_diff': my_goals-conceded, 'scorers': scorers}
            session['last_match_result']=copy.deepcopy(result)
            flash(f"{result['result']}! {st['club']} {result['score']} {result['opponent']}. Thưởng {format_money(result['reward'])}. Ngân sách: {format_money(st['budget'])}.")
        elif act=='formation':
            formation=request.form.get('formation')
            if formation not in {'4-3-3 (Tấn công)','4-3-3 (Phòng thủ)','4-2-4','4-1-2-1-2'}: raise ValueError('Sơ đồ không hợp lệ.')
            st['formation']=formation
            role_sets = {'4-3-3 (Tấn công)':['LW','ST','RW','CM','CAM','CM','LB','CB','CB','RB','GK'],'4-3-3 (Phòng thủ)':['LW','ST','RW','CM','CDM','CM','LB','CB','CB','RB','GK'],'4-2-4':['LW','ST','ST','RW','CM','CM','LB','CB','CB','RB','GK'],'4-1-2-1-2':['ST','ST','CAM','CM','CM','CDM','LB','CB','CB','RB','GK']}
            starters=st.get('starting',[])[:11]
            keeper=next((x for x in starters if str(x.get('position','')).upper()=='GK'),None)
            outfield=[x for x in starters if x is not keeper]
            roles=[r for r in role_sets[formation] if r!='GK']
            for player_obj,role in zip(outfield,roles): player_obj['assigned_position']=role
            if keeper: keeper['assigned_position']='GK'
            st['starting']=outfield + ([keeper] if keeper else [])
        else: raise ValueError('Thao tác không hợp lệ.')
        update_daily_quests(st, quest_event, quest_data)
        st.setdefault('activity',[]).insert(0,{'message':flash_message_placeholder(act),'week':st.get('week',1)})
        st['activity']=st['activity'][:15]
        persist(save,st)
    except (ValueError,KeyError,IndexError,TypeError) as e:
        db.session.rollback()
        if is_ajax and act == 'upgrade':
            return jsonify({'ok': False, 'error': str(e)}), 400
        flash(str(e))
    if is_ajax and act == 'upgrade' and upgrade_response:
        return jsonify({'ok': True, **upgrade_response})
    return redirect(request.referrer or url_for('dashboard'))
def flash_message_placeholder(act): return {'swap':'Cập nhật đội hình','promote':'Thêm cầu thủ vào đội hình','buy':'Chuyển nhượng','sell':'Bán cầu thủ','pack':'Mở gói cầu thủ','ballon_pack':'Mở Ballon D’or Pack','upgrade':'Ép thẻ','match':'Kết quả trận đấu','formation':'Đổi chiến thuật'}.get(act,'Hoạt động')
# ---------------- Academic League (A1 Cup) ----------------
from zoneinfo import ZoneInfo
A1_TZ = ZoneInfo('Asia/Ho_Chi_Minh')
A1_FIRST_START = datetime(2026, 11, 22, 18, 0)
A1_CUP_NAME = 'Academic League (A1 Cup)'


def a1_now():
    return datetime.now(A1_TZ).replace(tzinfo=None)


def a1_ranked_teams():
    ranked = []
    for account in User.query.filter_by(is_admin=False).order_by(User.id.asc()).all():
        save = GameSave.query.filter_by(user_id=account.id).first()
        if not save:
            continue
        state = load_state(save)
        if not state.get('starting'):
            continue
        data = get_dashboard(state)
        if float(data.get('average_rating', 0) or 0) <= 97:
            continue  # Match the eligibility rule of the server OVR leaderboard.
        ranked.append({
            'user_id': account.id, 'username': account.username,
            'club': state.get('custom_club_name') or state.get('club') or 'CLB',
            'ovr': float(data.get('average_rating', 0) or 0),
            'matches': int(data.get('matches_played', 0) or 0),
            'players': [str(x.get('name', 'Cầu thủ')) for x in state.get('starting', [])[:11]],
        })
    ranked.sort(key=lambda x: (x['ovr'], x['matches'], x['username'].casefold()), reverse=True)
    return ranked[:8]


def a1_schedule_for(start_at):
    # Fixed 14-match weekly calendar, all times are Vietnam local time.
    # start_at is Sunday 18:00; build fixtures from that Sunday's midnight.
    week_start = start_at.replace(hour=0, minute=0, second=0, microsecond=0)
    slots = [
        (0,18,15,'Tứ kết','A',1), (0,18,30,'Tứ kết','B',1),
        (1,19,45,'Tứ kết','C',1), (1,20,0,'Tứ kết','D',1),
        (2,19,45,'Tứ kết','A',2), (2,20,0,'Tứ kết','B',2),
        (3,19,45,'Tứ kết','C',2), (3,20,0,'Tứ kết','D',2),
        (4,19,45,'Bán kết','SF1',1), (4,20,0,'Bán kết','SF2',1),
        (5,19,45,'Bán kết','SF1',2), (5,20,0,'Bán kết','SF2',2),
        (6,10,50,'Tranh hạng 3','THIRD',1), (6,19,0,'Chung kết','FINAL',1),
    ]
    matches=[]
    for idx,(day,hour,minute,stage,pair,leg) in enumerate(slots,1):
        when=week_start + timedelta(days=day, hours=hour, minutes=minute)
        matches.append({'id':idx,'stage':stage,'pair':pair,'leg':leg,'starts_at':when.isoformat(timespec='minutes'),
                        'status':'scheduled','home':None,'away':None,'result':None})
    return matches


def a1_create_season(start_at):
    if A1CupSeason.query.filter_by(start_at=start_at).first():
        return None
    teams = a1_ranked_teams()
    if len(teams) < 8:
        app.logger.warning('A1 Cup: cần ít nhất 8 CLB có đội hình để bốc thăm; hiện có %s.', len(teams))
        return None
    shuffled = copy.deepcopy(teams)
    random.shuffle(shuffled)
    pairs = {letter: [shuffled[i], shuffled[i+1]] for letter,i in zip('ABCD', range(0,8,2))}
    matches = a1_schedule_for(start_at)
    for match in matches:
        if match['stage']=='Tứ kết':
            pair = pairs[match['pair']]
            match['home'] = copy.deepcopy(pair[0] if match['leg']==1 else pair[1])
            match['away'] = copy.deepcopy(pair[1] if match['leg']==1 else pair[0])
    season_no = (db.session.query(db.func.max(A1CupSeason.season_number)).scalar() or 0) + 1
    season = A1CupSeason(season_number=season_no, name=A1_CUP_NAME, start_at=start_at,
                         teams=copy.deepcopy(teams), matches=matches)
    db.session.add(season); db.session.commit()
    return season


def a1_current_club_name(user_id, fallback='CLB'):
    """Resolve a tournament participant's current club name from its live save.

    Tournament fixtures intentionally retain participant IDs and frozen sporting
    data (OVR/players), but the displayed club name must always follow profile renames.
    """
    try:
        save = GameSave.query.filter_by(user_id=int(user_id)).first()
        if save:
            state = load_state(save)
            return state.get('custom_club_name') or state.get('club') or fallback
    except (TypeError, ValueError):
        app.logger.warning('A1 Cup: invalid participant user_id %r', user_id)
    return fallback


def a1_refresh_display_names(season, matches, podium):
    """Refresh names in every historical/current bracket slot by stable user ID."""
    current_by_id = {}
    for team in (season.teams or []):
        uid = team.get('user_id')
        if uid is None:
            continue
        team['club'] = a1_current_club_name(uid, team.get('club', 'CLB'))
        current_by_id[str(uid)] = team

    for match in matches:
        for side in ('home', 'away'):
            team = match.get(side)
            if not team:
                continue
            current = current_by_id.get(str(team.get('user_id')))
            if current:
                team['club'] = current['club']
                team['club_label'] = current['club']

    for place in ('champion', 'runner_up', 'third'):
        team = podium.get(place)
        if team:
            current = current_by_id.get(str(team.get('user_id')))
            if current:
                team['club'] = current['club']
    return matches, podium


def a1_ensure_season():
    now = a1_now()
    latest = A1CupSeason.query.order_by(A1CupSeason.season_number.desc()).first()
    if latest is None:
        # Draw season 1 in advance for the fixed inaugural kickoff on Sunday 22/11/2026.
        # If the host wakes late, the scheduler catches up its overdue fixtures in order.
        a1_create_season(A1_FIRST_START)
        return
    next_start = latest.start_at + timedelta(days=7)
    if now >= next_start:
        a1_create_season(next_start)


def a1_roll_score(home, away):
    # Lightweight automatic match simulation using the frozen OVR from the draw.
    def goals(att, deff):
        lam = max(0.25, min(3.4, 1.35 + (float(att)-float(deff))*0.045 + random.uniform(-0.25,0.25)))
        p = math.exp(-lam); cumulative=p; r=random.random(); count=0
        while r>cumulative and count<7:
            count+=1; p*=lam/count; cumulative+=p
        return count
    return goals(home.get('ovr',60), away.get('ovr',60)), goals(away.get('ovr',60), home.get('ovr',60))


def a1_penalties(home, away):
    # Simulated shoot-out winner; no extra score is added to the match score.
    return home if random.random() < (0.5 + max(-0.12,min(0.12,(float(home.get('ovr',60))-float(away.get('ovr',60)))*0.008))) else away


def a1_match_result(home, away, allow_extra=False):
    gh,ga=a1_roll_score(home,away)
    extra_h=extra_a=0; penalty_winner=None; went_extra=bool(allow_extra and gh==ga)
    if went_extra:
        extra_h,extra_a=a1_roll_score({**home,'ovr':float(home.get('ovr',60))-2},{**away,'ovr':float(away.get('ovr',60))-2})
        # Extra-time score is intentionally limited to a small increment.
        extra_h=min(extra_h,2); extra_a=min(extra_a,2)
        gh+=extra_h; ga+=extra_a
        if gh==ga:
            penalty_winner=a1_penalties(home,away)
    scorer_h=random.sample(home.get('players') or [home['club']], min(gh, len(home.get('players') or [home['club']]))) if gh else []
    scorer_a=random.sample(away.get('players') or [away['club']], min(ga, len(away.get('players') or [away['club']]))) if ga else []
    return {'home_goals':gh,'away_goals':ga,'score':f'{gh} - {ga}',
            'extra_time':went_extra,
            'extra_time_score':f'{extra_h} - {extra_a}' if went_extra else None,
            'penalties':bool(penalty_winner), 'penalty_winner_id':penalty_winner.get('user_id') if penalty_winner else None,
            'winner_id':(home if gh>ga else away if ga>gh else penalty_winner).get('user_id') if (gh!=ga or penalty_winner) else None,
            'scorers_home':scorer_h,'scorers_away':scorer_a}


def a1_pair_winner(season, pair):
    legs=[m for m in (season.matches or []) if m['stage']=='Tứ kết' and m['pair']==pair and m['status']=='completed']
    if len(legs)<2: return None
    totals={}
    for m in legs:
        h,a=m['home'],m['away']; r=m['result']
        totals[h['user_id']]=totals.get(h['user_id'],0)+r['home_goals']
        totals[a['user_id']]=totals.get(a['user_id'],0)+r['away_goals']
    if totals[legs[0]['home']['user_id']] == totals[legs[0]['away']['user_id']]:
        winner_id=legs[1]['result'].get('winner_id')
        return next((x for x in season.teams if x['user_id']==winner_id),None)
    winner_id=max(totals,key=totals.get)
    return next((x for x in season.teams if x['user_id']==winner_id),None)


def a1_set_match_teams(season, pair, home, away):
    for m in season.matches:
        if m['pair']==pair and m['stage'] in ('Bán kết','Tranh hạng 3','Chung kết'):
            if m['leg']==1:
                m['home']=copy.deepcopy(home); m['away']=copy.deepcopy(away)
            else:
                m['home']=copy.deepcopy(away); m['away']=copy.deepcopy(home)


def a1_refresh_bracket(season):
    # Fill the two semi-final ties once all quarter-final return legs are complete.
    qf_done=all(any(m['pair']==p and m['leg']==2 and m['status']=='completed' for m in season.matches) for p in 'ABCD')
    if qf_done and not next((m for m in season.matches if m['pair']=='SF1' and m['home']),None):
        winners={p:a1_pair_winner(season,p) for p in 'ABCD'}
        if all(winners.values()):
            a1_set_match_teams(season,'SF1',winners['A'],winners['B'])
            a1_set_match_teams(season,'SF2',winners['C'],winners['D'])
    sf_done=all(any(m['pair']==p and m['leg']==2 and m['status']=='completed' for m in season.matches) for p in ('SF1','SF2'))
    if sf_done and not next((m for m in season.matches if m['pair']=='FINAL' and m['home']),None):
        def winner_of(pair):
            ms=[m for m in season.matches if m['pair']==pair and m['status']=='completed']
            if len(ms)<2:return None
            totals={}
            for m in ms:
                totals[m['home']['user_id']]=totals.get(m['home']['user_id'],0)+m['result']['home_goals']
                totals[m['away']['user_id']]=totals.get(m['away']['user_id'],0)+m['result']['away_goals']
            if totals[ms[0]['home']['user_id']]==totals[ms[0]['away']['user_id']]:
                return next((t for t in season.teams if t['user_id']==ms[1]['result'].get('winner_id')),None)
            return next((t for t in season.teams if t['user_id']==max(totals,key=totals.get)),None)
        winners=[winner_of('SF1'),winner_of('SF2')]
        if all(winners):
            losers=[]
            for pair,w in zip(('SF1','SF2'),winners):
                ms=[m for m in season.matches if m['pair']==pair and m['status']=='completed']
                team_ids={ms[0]['home']['user_id'],ms[0]['away']['user_id']}
                losers.append(next(t for t in season.teams if t['user_id'] in team_ids and t['user_id']!=w['user_id']))
            a1_set_match_teams(season,'FINAL',winners[0],winners[1])
            a1_set_match_teams(season,'THIRD',losers[0],losers[1])


def a1_award_prizes(season):
    if season.prizes_awarded: return
    final=next((m for m in season.matches if m['pair']=='FINAL' and m['status']=='completed'),None)
    third=next((m for m in season.matches if m['pair']=='THIRD' and m['status']=='completed'),None)
    if not final or not third: return
    champion_id=final['result']['winner_id']
    runner_id=final['away']['user_id'] if final['home']['user_id']==champion_id else final['home']['user_id']
    third_id=third['result']['winner_id']
    season.champion_user_id=champion_id; season.runner_up_user_id=runner_id; season.third_user_id=third_id
    rewards={champion_id:(5000,20000),runner_id:(3000,10000),third_id:(1000,5000)}
    for uid,(pc_m,pg) in rewards.items():
        save=GameSave.query.filter_by(user_id=uid).first()
        if not save: continue
        st=normalize_state(copy.deepcopy(save.state or {}))
        st['budget']=round(float(st.get('budget',0) or 0)+pc_m,2)
        st['pg_balance']=int(st.get('pg_balance',0) or 0)+pg
        st.setdefault('activity',[]).insert(0,{'message':f'Nhận thưởng Academic League (A1 Cup): +{pc_m*1000000:,.0f} PC và +{pg:,} PG','week':st.get('week',1)})
        st['activity']=st['activity'][:15]
        save.state=copy.deepcopy(st)
        db.session.add(save)
    season.prizes_awarded=True


def a1_process_due_matches():
    with app.app_context():
        try:
            a1_ensure_season()
            seasons=A1CupSeason.query.order_by(A1CupSeason.season_number.asc()).with_for_update().all()
            if not seasons: return
            now=a1_now(); any_changed=False
            # Process every season in order. If the host was asleep, overdue fixtures
            # are simulated chronologically instead of silently abandoning a week.
            for season in seasons:
                changed=False
                for m in sorted(season.matches or [], key=lambda x:(x['starts_at'],x['id'])):
                    scheduled=datetime.fromisoformat(m['starts_at'])
                    if m['status']!='scheduled' or scheduled>now: continue
                    if not m.get('home') or not m.get('away'): continue
                    allow_extra=m['pair'] in ('FINAL','THIRD')
                    result=a1_match_result(m['home'],m['away'],allow_extra=allow_extra)
                    if m['stage'] in ('Tứ kết','Bán kết') and m['leg']==2:
                        # Penalties decide a tie on aggregate after the second leg.
                        previous=next((x for x in season.matches if x['pair']==m['pair'] and x['leg']==1 and x['status']=='completed'),None)
                        if previous:
                            first_home_total=previous['result']['home_goals'] + result['away_goals']
                            first_away_total=previous['result']['away_goals'] + result['home_goals']
                            if first_home_total==first_away_total:
                                winner=a1_penalties(m['home'],m['away'])
                                result['penalties']=True; result['penalty_winner_id']=winner['user_id']; result['winner_id']=winner['user_id']
                            else:
                                # In the return leg, the first-leg home team is the away team.
                                result['winner_id']=m['away']['user_id'] if first_home_total>first_away_total else m['home']['user_id']
                    m['result']=result; m['status']='completed'; m['played_at']=now.isoformat(timespec='minutes')
                    changed=True
                    a1_refresh_bracket(season)
                if changed:
                    a1_award_prizes(season)
                    season.matches=copy.deepcopy(season.matches)
                    db.session.add(season)
                    any_changed=True
            if any_changed:
                db.session.commit()
        except Exception:
            db.session.rollback(); app.logger.exception('A1 Cup scheduler failed')


def a1_start_scheduler():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        if getattr(app,'_a1_scheduler',None): return
        scheduler=BackgroundScheduler(timezone=A1_TZ, daemon=True)
        scheduler.add_job(a1_process_due_matches,'interval',seconds=15,id='a1_cup_tick',max_instances=1,coalesce=True)
        scheduler.start(); app._a1_scheduler=scheduler
        a1_process_due_matches()
    except Exception:
        app.logger.exception('Could not start A1 Cup background scheduler')


@app.route('/tournament')
@login_required
def tournament():
    if current_user.is_admin:
        return redirect(url_for('admin_panel'))
    season=A1CupSeason.query.order_by(A1CupSeason.season_number.desc()).first()
    if not season:
        a1_ensure_season(); season=A1CupSeason.query.order_by(A1CupSeason.season_number.desc()).first()
    matches=[]
    podium={}
    if season:
        teams_by_id={t['user_id']:t for t in (season.teams or [])}
        podium={
            'champion':teams_by_id.get(season.champion_user_id),
            'runner_up':teams_by_id.get(season.runner_up_user_id),
            'third':teams_by_id.get(season.third_user_id),
        }
        matches=copy.deepcopy(season.matches or [])
        weekday_vi=['Thứ 2','Thứ 3','Thứ 4','Thứ 5','Thứ 6','Thứ 7','Chủ nhật']
        matches, podium = a1_refresh_display_names(season, matches, podium)
        for m in matches:
            dt=datetime.fromisoformat(m['starts_at'])
            m['starts_label']=f"{weekday_vi[dt.weekday()]} {dt.strftime('%d/%m · %H:%M')}"
            for side in ('home','away'):
                if m.get(side):
                    m[side]['club_label']=m[side].get('club','CLB')
    return render_template('tournament.html',season=season,matches=matches,podium=podium,now=a1_now())

@app.route('/match-3d')
@login_required
def match_3d():
    return render_template('match_3d.html')

# Scheduler is started once the full module (including A1 Cup functions) has loaded.
a1_start_scheduler()

if __name__=='__main__': app.run(debug=True)
