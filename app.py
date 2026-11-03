import os, random, copy, math, secrets, hmac
from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, GameSave
from game_engine import (CLUBS, create_new_game, get_dashboard, all_players, normalize_state,
                         TRANSFER_MARKET, PLAYER_PRICES, PLAYER_RATINGS, PLAYER_POSITIONS,
                         PACKS, UPGRADE_RATES, UPGRADE_COSTS, CARD_VALUE_RATES, value, player, simulate_match)

app = Flask(__name__)
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
    if 'is_admin' not in {column['name'] for column in inspect(db.engine).get_columns('user')}:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE "user" ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE'))
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
    euros = int(round(float(amount or 0) * 1_000_000))
    return f"{euros:,}".replace(',', '.') + ' €'

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
    match_popup=session.pop('last_match_result', None)
    return render_template('game.html', state=st, data=get_dashboard(st), tab=tab, players=all_players(st), match_popup=match_popup,
                           prices={p['name']:value(p) for p in all_players(st)}, packs=PACKS,
                           market=st['market'], market_items=[{'name':n,'position':PLAYER_POSITIONS.get(n,'ST'),'rating':PLAYER_RATINGS.get(n,80),'price':PLAYER_PRICES.get(n,0)} for n in st['market'] if n not in {p['name'] for p in all_players(st)} and n not in PACKS['4']['players']], upgrade_rates=UPGRADE_RATES, upgrade_costs=UPGRADE_COSTS, extra=extra)

@app.route('/')
def home(): return redirect(url_for('dashboard')) if current_user.is_authenticated else render_template('home.html')
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
        if user and user.check_password(request.form.get('password','')): login_user(user); return redirect(url_for('dashboard'))
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
    player_names = sorted(set(PLAYER_RATINGS) | set(PLAYER_POSITIONS) | set(TRANSFER_MARKET))
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
        position = request.form.get('position', PLAYER_POSITIONS.get(name, 'ST')).upper()
        if not 40 <= rating <= 99 or not 0 <= level <= 5:
            raise ValueError('OVR phải từ 40–99 và cấp thẻ từ +0 đến +5.')
        if position not in {'GK','CB','LB','RB','LWB','RWB','CDM','CM','CAM','LM','RM','LW','RW','ST','CF'}:
            raise ValueError('Vị trí cầu thủ không hợp lệ.')
        state = load_state(save)
        owned = [p for group in ('starting','bench','extras') for p in state.get(group, [])]
        if any(p.get('name') == name for p in owned):
            raise ValueError(f'{recipient.username} đã sở hữu {name}.')
        gifted = {'name': name, 'position': position, 'rating': rating, 'level': level}
        state.setdefault('extras', []).append(gifted)
        state.setdefault('activity', []).insert(0, {'message': f'Admin tặng {name} OVR {rating} +{level}', 'week': state.get('week', 1)})
        state['activity'] = state['activity'][:15]
        persist(save, state)
        flash(f'Đã tặng {name} OVR {rating} +{level} cho tài khoản {recipient.username}.')
    except (ValueError, TypeError) as error:
        flash(str(error))
    return redirect(url_for('admin_panel'))

@app.post('/admin/budget')
@admin_required
def admin_budget():
    if not valid_admin_csrf():
        flash('Phiên thao tác hết hạn. Hãy tải lại trang Admin.')
        return redirect(url_for('admin_panel'))
    try:
        user_id = int(request.form.get('user_id', ''))
        amount = float(request.form.get('amount', '0'))
        if amount <= 0 or amount > 100000:
            raise ValueError('Số tiền tặng phải lớn hơn 0 và không quá 100.000 triệu €.')
        save = GameSave.query.filter_by(user_id=user_id).first()
        recipient = db.session.get(User, user_id)
        if not save or not recipient:
            raise ValueError('Không tìm thấy dữ liệu game của tài khoản này.')
        state = load_state(save)
        state['budget'] = round(float(state.get('budget', 0)) + amount, 2)
        state.setdefault('activity', []).insert(0, {'message': f'Admin tặng €{amount:g}M', 'week': state.get('week', 1)})
        state['activity'] = state['activity'][:15]
        persist(save, state)
        flash(f'Đã tặng €{amount:g}M cho tài khoản {recipient.username}.')
    except (ValueError, TypeError) as error:
        flash(str(error))
    return redirect(url_for('admin_panel'))

@app.post('/action')
@login_required
def action():
    save=current_save()
    if not save: return redirect(url_for('choose_club'))
    st=load_state(save); act=request.form.get('action'); result=None
    try:
        if act=='swap':
            a=int(request.form['a']); b=int(request.form['b'])
            out=st['starting'][a]; inn=st['bench'][b]
            if out['position']!=inn['position']: raise ValueError('Chỉ được thay cầu thủ cùng vị trí.')
            st['starting'][a],st['bench'][b]=inn,out; flash(f"Đã thay {out['name']} bằng {inn['name']}.")
        elif act=='buy':
            name=request.form.get('name','').strip()
            if name not in st['market'] or name in PACKS['4']['players']: raise ValueError('Cầu thủ không có trên TTCN thông thường.')
            if any(x['name']==name for x in all_players(st)): raise ValueError('Bạn đã sở hữu cầu thủ này.')
            cost=float(PLAYER_PRICES.get(name,0))
            if cost <= 0: raise ValueError('Giá cầu thủ không hợp lệ.')
            if st['budget'] + 1e-9 < cost: raise ValueError(f'Không đủ ngân sách. Cần €{cost:g}M, hiện có €{st["budget"]:g}M.')
            st['budget']=round(st['budget']-cost,2); st['bench'].append(player(name)); st['market'].remove(name)
            flash(f'Chiêu mộ thành công {name}. Đã trừ {format_money(cost)}. Ngân sách còn {format_money(st["budget"])}.')
        elif act=='sell':
            group=request.form.get('group'); idx=int(request.form['index'])
            if group not in {'bench','extras'}: raise ValueError('Không thể bán cầu thủ ở danh sách này.')
            arr=st[group]; p=arr[idx]; amount=float(value(p))
            arr.pop(idx); st['budget']=round(st['budget']+amount,2)
            if p['name'] not in st['market'] and p['name'] not in PACKS['4']['players']: st['market'].append(p['name'])
            flash(f'Đã bán {p["name"]}, cộng {format_money(amount)}. Ngân sách: {format_money(st["budget"])}.')
        elif act=='pack':
            key=request.form.get('pack')
            if key not in PACKS: raise ValueError('Gói cầu thủ không hợp lệ.')
            pack=PACKS[key]; cost=float(pack['price'])
            if st['budget'] + 1e-9 < cost: raise ValueError(f'Không đủ ngân sách. Gói giá €{cost:g}M, anh hiện có €{st["budget"]:g}M.')
            p=random.choice(pack['players'])
            st['budget']=round(st['budget']-cost,2); st['bench'].append(player(p))
            flash(f'Mở {pack["name"]}: nhận được {p}! Đã trừ {format_money(cost)}, còn {format_money(st["budget"])}.')
        elif act=='upgrade':
            group=request.form.get('group'); idx=int(request.form['index'])
            if group not in {'starting','bench','extras'}: raise ValueError('Danh sách cầu thủ không hợp lệ.')
            p=st[group][idx]; level=int(p.get('level',0))
            if level>=5: raise ValueError('Cầu thủ đã đạt +5.')
            target=level+1; cost=round(UPGRADE_COSTS[target]*p['rating']/90,2)
            if st['budget'] + 1e-9 < cost: raise ValueError(f'Không đủ ngân sách ép thẻ. Cần {format_money(cost)}.')
            st['budget']=round(st['budget']-cost,2)
            success=random.randint(1,100)<=UPGRADE_RATES[level]
            old_level=level
            p['level']=target if success else (0 if level==0 else random.randint(0,level-1))
            if success: flash(f'🎉 ÉP THẺ THÀNH CÔNG! {p["name"]} lên +{p["level"]}. Đã trừ {format_money(cost)}; ngân sách còn {format_money(st["budget"])}.')
            else: flash(f'ÉP THẺ THẤT BẠI! {p["name"]} từ +{old_level} xuống +{p["level"]}. Đã trừ {format_money(cost)}; ngân sách còn {format_money(st["budget"])}.')
        elif act=='match':
            result=simulate_match(st)
            session['last_match_result']=copy.deepcopy(result)
            flash(f"{result['result']}! {st['club']} {result['score']} {result['opponent']}. Thưởng {format_money(result['reward'])}. Ngân sách: {format_money(st['budget'])}.")
        elif act=='formation':
            formation=request.form.get('formation')
            if formation not in {'4-3-3','4-4-2','4-2-3-1'}: raise ValueError('Sơ đồ không hợp lệ.')
            st['formation']=formation; flash('Đã cập nhật sơ đồ chiến thuật.')
        else: raise ValueError('Thao tác không hợp lệ.')
        st.setdefault('activity',[]).insert(0,{'message':flash_message_placeholder(act),'week':st.get('week',1)})
        st['activity']=st['activity'][:15]
        persist(save,st)
    except (ValueError,KeyError,IndexError,TypeError) as e:
        db.session.rollback(); flash(str(e))
    return redirect(request.referrer or url_for('dashboard'))
def flash_message_placeholder(act): return {'swap':'Cập nhật đội hình','buy':'Chuyển nhượng','sell':'Bán cầu thủ','pack':'Mở gói cầu thủ','upgrade':'Ép thẻ','match':'Kết quả trận đấu','formation':'Đổi chiến thuật'}.get(act,'Hoạt động')
if __name__=='__main__': app.run(debug=True)
