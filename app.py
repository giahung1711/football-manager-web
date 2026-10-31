import os, random
from flask import Flask, render_template, redirect, url_for, request, flash
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
with app.app_context(): db.create_all()

def current_save(): return GameSave.query.filter_by(user_id=current_user.id).first()
def load_state(save):
    state=normalize_state(save.state)
    if state != save.state: save.state=state; db.session.commit()
    return state
def persist(save,state): save.state=state; db.session.commit()
def page(save, tab='overview', extra=None):
    st=load_state(save)
    return render_template('game.html', state=st, data=get_dashboard(st), tab=tab, players=all_players(st),
                           prices={p['name']:value(p) for p in all_players(st)}, packs=PACKS,
                           market=st['market'], market_items=[{'name':n,'position':PLAYER_POSITIONS.get(n,'ST'),'rating':PLAYER_RATINGS.get(n,80),'price':PLAYER_PRICES.get(n,0)} for n in st['market'] if n not in {p['name'] for p in all_players(st)}], upgrade_rates=UPGRADE_RATES, upgrade_costs=UPGRADE_COSTS, extra=extra)

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
@app.post('/action')
@login_required
def action():
    save=current_save()
    if not save: return redirect(url_for('choose_club'))
    st=load_state(save); act=request.form.get('action'); result=None
    try:
        if act=='swap':
            a=int(request.form['a']); b=int(request.form['b']); out=st['starting'][a]; inn=st['bench'][b]
            if out['position']!=inn['position']: raise ValueError('Chỉ được thay cầu thủ cùng vị trí.')
            st['starting'][a],st['bench'][b]=inn,out; flash(f"Đã thay {out['name']} bằng {inn['name']}.")
        elif act=='buy':
            name=request.form['name']; available=[x for x in st['market'] if x==name]
            if not available: raise ValueError('Cầu thủ không còn trên thị trường.')
            p=player(name); cost=PLAYER_PRICES.get(name,0)
            if any(x['name']==name for x in all_players(st)): raise ValueError('Bạn đã sở hữu cầu thủ này.')
            if st['budget']<cost: raise ValueError('Ngân sách không đủ.')
            st['budget']-=cost; st['extras'].append(p); st['market'].remove(name); flash(f'Chiêu mộ thành công {name}, giá €{cost}M.')
        elif act=='sell':
            group= request.form['group']; idx=int(request.form['index']); arr=st[group]; p=arr[idx]
            if group=='starting' and len(st['starting'])<=11: raise ValueError('Không thể bán cầu thủ đá chính nếu chưa có người thay thế.')
            if group=='starting': raise ValueError('Hãy đưa cầu thủ ra dự bị trước khi bán.')
            amount=value(p); arr.pop(idx); st['budget']+=amount
            if p['name'] not in st['market']: st['market'].append(p['name'])
            flash(f'Đã bán {p["name"]}, thu về €{amount}M.')
        elif act=='pack':
            key=request.form['pack']; pack=PACKS[key]
            if st['budget']<pack['price']: raise ValueError('Ngân sách không đủ mua gói.')
            p=random.choice(pack['players']); st['budget']-=pack['price']; st['extras'].append(player(p)); flash(f"Mở {pack['name']}: nhận được {p}!")
        elif act=='upgrade':
            group=request.form['group']; idx=int(request.form['index']); p=st[group][idx]; level=p.get('level',0)
            if level>=5: raise ValueError('Cầu thủ đã đạt +5.')
            target=level+1; cost=round(UPGRADE_COSTS[target]*p['rating']/90,2)
            if st['budget']<cost: raise ValueError('Không đủ ngân sách ép thẻ.')
            st['budget']-=cost
            success=random.randint(1,100)<=UPGRADE_RATES[level]
            p['level']=target if success else (0 if level==0 else random.randint(0,level-1))
            flash((f'Ép thẻ thành công: {p["name"]} +{p["level"]}.' if success else f'Ép thẻ thất bại: {p["name"]} còn +{p["level"]}.'))
        elif act=='match':
            result=simulate_match(st); flash(f"{result['result']}! {st['club']} {result['score']} {result['opponent']}. Thưởng €{result['reward']}M.")
        elif act=='formation':
            formation=request.form.get('formation')
            if formation not in {'4-3-3','4-4-2','4-2-3-1'}: raise ValueError('Sơ đồ không hợp lệ.')
            st['formation']=formation; flash('Đã cập nhật sơ đồ chiến thuật.')
        else: raise ValueError('Thao tác không hợp lệ.')
        st.setdefault('activity',[]).insert(0,{'message':flash_message_placeholder(act),'week':st.get('week',1)})
        st['activity']=st['activity'][:15]
        persist(save,st)
    except (ValueError,KeyError,IndexError) as e: flash(str(e))
    return redirect(request.referrer or url_for('dashboard'))
def flash_message_placeholder(act): return {'swap':'Cập nhật đội hình','buy':'Chuyển nhượng','sell':'Bán cầu thủ','pack':'Mở gói cầu thủ','upgrade':'Ép thẻ','match':'Kết quả trận đấu','formation':'Đổi chiến thuật'}.get(act,'Hoạt động')
if __name__=='__main__': app.run(debug=True)
