import os, random, copy, math, secrets, hmac
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, GameSave, FriendRequest, Friendship, FriendlyChallenge
from marketplace import player_market_bp
from player_metadata import enrich_player, get_player_metadata
from game_engine import (CLUBS, create_new_game, get_dashboard, all_players, normalize_state,
                         TRANSFER_MARKET, PLAYER_PRICES, PLAYER_RATINGS, PLAYER_POSITIONS,
                         PACKS, UPGRADE_RATES, UPGRADE_COSTS, CARD_VALUE_RATES, UPGRADE_FAILURE_DISTRIBUTION, MAX_UPGRADE_LEVEL, upgrade_cost, value, player, simulate_match)

app = Flask(__name__)
app.register_blueprint(player_market_bp)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-secret-key-before-deploying')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///football_manager.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
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
    # Metadata is resolved from the connected football-data provider and cached for 12h.
    # Saved squad records remain untouched; unknown/incomplete players are not rendered as verified cards.
    for group in ('starting', 'bench', 'extras'):
        st[group] = [enrich_player(p) for p in st.get(group, [])]
    market_items=[]
    # Only resolve transfer-market cards when the transfer page is requested.
    # Queueing every market player on dashboard/squad renders wastes API quota.
    if tab == 'transfers':
        owned_names = {p['name'] for p in all_players(st)}
        for n in st['market']:
            if n in owned_names or n in PACKS['4']['players']:
                continue
            meta = get_player_metadata(n)
            if not meta or not all(meta.get(k) for k in ('nationality','club','league')):
                continue
            market_items.append({'name':n,'position':PLAYER_POSITIONS.get(n,'ST'),'rating':PLAYER_RATINGS.get(n,80),'price':PLAYER_PRICES.get(n,0), **meta})
    match_popup=session.pop('last_match_result', None)
    ballon_reveal = st.pop('ballon_reveal', None)
    ballon_reveal_meta = enrich_player(ballon_reveal) if ballon_reveal else None
    if ballon_reveal:
        persist(save, st)
    return render_template('game.html', state=st, data=get_dashboard(st), tab=tab, players=all_players(st), match_popup=match_popup,
                           prices={p['name']:value(p) for p in all_players(st)}, packs=PACKS,
                           market=st['market'], market_items=market_items, ballon_reveal=ballon_reveal, ballon_reveal_meta=ballon_reveal_meta, ballon_request_id=secrets.token_urlsafe(18), upgrade_rates=UPGRADE_RATES, upgrade_costs=UPGRADE_COSTS, extra=extra)

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
@app.route('/<tab>')
@login_required
def game_tab(tab):
    if tab not in {'squad','transfers','shop','upgrade','tactics','finance','matches'}: return redirect(url_for('dashboard'))
    save=current_save(); return redirect(url_for('choose_club')) if not save else page(save,tab)
@app.route('/admin', methods=['GET'])
@admin_required
def admin_panel():
    users = User.query.order_by(User.created_at.desc()).all()
    player_names = set(PLAYER_RATINGS) | set(PLAYER_POSITIONS) | set(TRANSFER_MARKET)
    # Include players already present in any saved squad.
    for save in GameSave.query.all():
        state = save.state or {}
        for group in ('starting', 'bench', 'extras'):
            player_names.update(p.get('name', '') for p in state.get(group, []) if p.get('name'))
    return render_template('admin.html', users=users, player_names=sorted(player_names))

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
        nationality = request.form.get('nationality', '').strip()[:80]
        club = request.form.get('player_club', '').strip()[:100]
        league = request.form.get('player_league', '').strip()[:100]
        card_type = request.form.get('card_type', 'REGULAR').upper()
        career_status = request.form.get('career_status', 'active').lower()
        source_url = request.form.get('metadata_source_url', '').strip()[:500]
        photo_url = request.form.get('photo_url', '').strip()[:500]
        if photo_url:
            from urllib.parse import urlparse
            parsed_photo = urlparse(photo_url)
            if parsed_photo.scheme != 'https' or not parsed_photo.netloc:
                raise ValueError('Ảnh cầu thủ phải dùng đường dẫn HTTPS hợp lệ.')
        allowed_types = {'REGULAR', 'HEROES', 'ICON'}
        if rating < 1 or level < 0 or not math.isfinite(transfer_value) or transfer_value < 0:
            raise ValueError('OVR/cấp thẻ không hợp lệ hoặc giá trị chuyển nhượng bị âm.')
        if position not in {'GK','CB','LB','RB','LWB','RWB','CDM','CM','CAM','LM','RM','LW','RW','ST','CF'}:
            raise ValueError('Vị trí cầu thủ không hợp lệ.')
        if card_type not in allowed_types or career_status not in {'active', 'retired'}:
            raise ValueError('Phân loại thẻ hoặc trạng thái sự nghiệp không hợp lệ.')
        if not nationality:
            raise ValueError('Phải nhập quốc gia đã xác minh của cầu thủ.')
        if career_status == 'active' and (not club or not league):
            raise ValueError('Cầu thủ còn thi đấu cấp CLB phải có CLB và giải đấu hiện tại.')
        if career_status == 'retired' and card_type not in {'ICON', 'HEROES'}:
            raise ValueError('Cầu thủ giải nghệ hoàn toàn phải được phân loại ICON hoặc HEROES mới được gift theo quy tắc hiện tại.')
        if card_type in {'ICON', 'HEROES'}:
            from urllib.parse import urlparse
            parsed_source = urlparse(source_url)
            trusted_domains = ('fifa.com', 'uefa.com', 'worldfootball.net', 'rsssf.org', 'transfermarkt.com', 'premierleague.com', 'laliga.com', 'bundesliga.com', 'ligue1.com', 'seriea.com', 'the-afc.com', 'conmebol.com', 'concacaf.com', 'cafonline.com')
            host = (parsed_source.hostname or '').lower()
            if parsed_source.scheme != 'https' or not any(host == d or host.endswith('.' + d) for d in trusted_domains):
                raise ValueError('ICON/HEROES cần đường dẫn HTTPS từ nguồn bóng đá uy tín (FIFA, UEFA, WorldFootball, RSSSF, Transfermarkt hoặc trang giải đấu/liên đoàn chính thức).')
        state = load_state(save)
        owned = [p for group in ('starting','bench','extras') for p in state.get(group, [])]
        pending_names = [m.get('player', {}).get('name') for m in state.get('mailbox', []) if m.get('type') == 'player_gift' and not m.get('opened')]
        if any(p.get('name') == name for p in owned) or name in pending_names:
            raise ValueError(f'{recipient.username} đã sở hữu hoặc đang có thư tặng {name}.')
        gifted = {
            'name': name, 'position': position, 'rating': rating, 'level': level,
            'market_value': transfer_value, 'nationality': nationality,
            'club': club if career_status == 'active' else '',
            'league': league if career_status == 'active' else '',
            'card_type': card_type, 'career_status': career_status,
            'metadata_source_url': source_url, 'metadata_admin_verified': True,
            'photo_url': photo_url,
            'is_icon': card_type == 'ICON', 'is_hero': card_type == 'HEROES',
            'metadata_complete': True,
        }
        subject = request.form.get('mail_subject', '').strip()[:100] or 'Bạn nhận được một gói cầu thủ!'
        body = request.form.get('mail_body', '').strip()[:1000] or 'Admin gửi tặng bạn một cầu thủ. Nhấn Mở để nhận vào đội hình dự bị.'
        mail = {'id': secrets.token_urlsafe(12), 'type': 'player_gift', 'subject': subject, 'body': body,
                'player': gifted, 'opened': False, 'created_at': datetime.utcnow().strftime('%d/%m/%Y %H:%M')}
        state.setdefault('mailbox', []).insert(0, mail)
        state.setdefault('activity', []).insert(0, {'message': f'Admin gửi thư tặng {name} OVR {rating} +{level}', 'week': state.get('week', 1)})
        state['activity'] = state['activity'][:15]
        persist(save, state)
        flash(f'Đã gửi gói {name} vào hòm thư của {recipient.username}.')
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
    elif mail.get('type') == 'player_gift':
        gifted = copy.deepcopy(mail.get('player') or {})
        if not gifted.get('name'):
            flash('Gói quà trong thư không hợp lệ.')
        elif any(p.get('name') == gifted['name'] for group in ('starting','bench','extras') for p in state.get(group, [])):
            mail['opened'] = True
            flash('Cầu thủ này đã có trong đội hình; thư được đánh dấu đã xử lý để tránh nhận trùng.')
        else:
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
        if mail.get('opened') or mail.get('type') != 'player_gift':
            continue
        gifted = copy.deepcopy(mail.get('player') or {})
        if not gifted.get('name'):
            mail['opened'] = True
            continue
        if any(p.get('name') == gifted['name'] for group in ('starting','bench','extras') for p in state.get(group, [])):
            mail['opened'] = True
            continue
        state.setdefault('bench', []).append(gifted)
        mail['opened'] = True
        received.append(gifted['name'])
    if received:
        state.setdefault('activity', []).insert(0, {'message': f'Nhận {len(received)} cầu thủ từ hòm thư', 'week': state.get('week', 1)})
        state['activity'] = state['activity'][:15]
        flash('Đã nhận: ' + ', '.join(received) + ' vào đội hình dự bị.')
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
    starters = state.get('starting', [])
    ovr_values = [float(x.get('rating', 0)) + float(x.get('level', 0)) for x in starters]
    online = bool(user.last_seen_at and user.last_seen_at >= datetime.utcnow() - timedelta(seconds=90))
    return {'user': user, 'state': state, 'history': history, 'wins': wins, 'draws': draws, 'losses': losses,
            'ovr': round(sum(ovr_values)/len(ovr_values), 1) if ovr_values else 0, 'online': online}

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
    squad = state.get('starting', []) + state.get('bench', []) + state.get('extras', [])
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
    st=load_state(save); act=request.form.get('action'); result=None
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
            if any(x['name']==name for x in all_players(st)): raise ValueError('Bạn đã sở hữu cầu thủ này.')
            cost=float(PLAYER_PRICES.get(name,0))
            if cost <= 0: raise ValueError('Giá cầu thủ không hợp lệ.')
            if st['budget'] + 1e-9 < cost: raise ValueError(f'Không đủ ngân sách. Cần 🪙 {cost:g}M PC, hiện có 🪙 {st["budget"]:g}M PC.')
            st['budget']=round(st['budget']-cost,2); st['bench'].append(player(name)); st['market'].remove(name)
            flash(f'Chiêu mộ thành công {name}. Đã trừ {format_money(cost)}. Ngân sách còn {format_money(st["budget"])}.')
        elif act=='sell':
            group=request.form.get('group'); idx=int(request.form['index'])
            if group not in {'bench','extras'}: raise ValueError('Không thể bán cầu thủ ở danh sách này.')
            arr=st[group]; p=arr[idx]; amount=float(value(p))
            arr.pop(idx); st['budget']=round(st['budget']+amount,2)
            if p['name'] not in st['market'] and p['name'] not in PACKS['4']['players']: st['market'].append(p['name'])
            flash(f'Đã bán {p["name"]}, cộng {format_money(amount)}. Ngân sách: {format_money(st["budget"])}.')

        elif act=='ballon_pack':
            # Server-side one-time token prevents a browser double-submit from charging twice.
            request_id = request.form.get('request_id', '').strip()
            if not request_id or len(request_id) > 100:
                raise ValueError('Yêu cầu mở gói không hợp lệ. Hãy tải lại trang.')
            processed = st.setdefault('processed_ballon_requests', [])
            if request_id in processed:
                flash('Gói này đã được xử lý trước đó.')
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
                       'card_season': 'Ballon D’or'}
            st['pg_balance'] = int(st.get('pg_balance', 0)) - cost_pg
            st.setdefault('bench', []).append(awarded)
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
            flash(f'Đã mở Ballon D’or Pack và nhận {name} OVR {rating}!')

        elif act=='pack':
            key=request.form.get('pack')
            if key not in PACKS: raise ValueError('Gói cầu thủ không hợp lệ.')
            pack=PACKS[key]; cost=float(pack['price'])
            if st['budget'] + 1e-9 < cost: raise ValueError(f'Không đủ ngân sách. Gói giá 🪙 {cost:g}M PC, bạn hiện có 🪙 {st["budget"]:g}M PC.')
            p=random.choice(pack['players'])
            st['budget']=round(st['budget']-cost,2); st['bench'].append(player(p))
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
            if success:
                flash(f'🎉 ÉP THẺ THÀNH CÔNG! {p["name"]} lên +{new_level}. Đã trừ {format_money(cost)}; ngân sách còn {format_money(st["budget"])}.')
            elif protection_requested:
                flash(f'ÉP THẺ THẤT BẠI! {p["name"]} giữ nguyên +7 nhờ Thẻ bảo vệ. Đã tiêu hao 1 Thẻ bảo vệ và trừ {format_money(cost)}.')
            else:
                flash(f'ÉP THẺ THẤT BẠI! {p["name"]} từ +{old_level} xuống +{new_level}. Đã trừ {format_money(cost)}; ngân sách còn {format_money(st["budget"])}.')
            st['last_upgrade_summary'] = {
                'player': p.get('name'), 'attempts': total_attempts,
                'successes': total_successes, 'spent': round(total_spent, 2)
            }
        elif act=='match':
            result=simulate_match(st)
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
        st.setdefault('activity',[]).insert(0,{'message':flash_message_placeholder(act),'week':st.get('week',1)})
        st['activity']=st['activity'][:15]
        persist(save,st)
    except (ValueError,KeyError,IndexError,TypeError) as e:
        db.session.rollback(); flash(str(e))
    return redirect(request.referrer or url_for('dashboard'))
def flash_message_placeholder(act): return {'swap':'Cập nhật đội hình','promote':'Thêm cầu thủ vào đội hình','buy':'Chuyển nhượng','sell':'Bán cầu thủ','pack':'Mở gói cầu thủ','ballon_pack':'Mở Ballon D’or Pack','upgrade':'Ép thẻ','match':'Kết quả trận đấu','formation':'Đổi chiến thuật'}.get(act,'Hoạt động')
if __name__=='__main__': app.run(debug=True)
