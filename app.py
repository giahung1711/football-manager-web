import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, GameSave
from game_engine import CLUBS, create_new_game, get_dashboard, get_squad

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key-before-deploying")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///football_manager.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Some hosting providers supply postgres://; SQLAlchemy expects postgresql://.
if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgres://"):
    app.config["SQLALCHEMY_DATABASE_URI"] = app.config["SQLALCHEMY_DATABASE_URI"].replace("postgres://", "postgresql://", 1)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

with app.app_context():
    db.create_all()

@app.route("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("home.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if len(username) < 3:
            flash("Tên tài khoản phải có ít nhất 3 ký tự.")
        elif len(password) < 8:
            flash("Mật khẩu phải có ít nhất 8 ký tự.")
        elif User.query.filter_by(username=username).first():
            flash("Tên tài khoản đã được sử dụng.")
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for("choose_club"))
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Tên tài khoản hoặc mật khẩu không đúng.")
    return render_template("auth.html", mode="login")

@app.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

def current_save():
    return GameSave.query.filter_by(user_id=current_user.id).first()

@app.route("/choose-club", methods=["GET", "POST"])
@login_required
def choose_club():
    save = current_save()
    if save:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        club = request.form.get("club")
        if club not in CLUBS:
            flash("Vui lòng chọn một câu lạc bộ hợp lệ.")
        else:
            state = create_new_game(club)
            save = GameSave(user_id=current_user.id, state=state)
            db.session.add(save)
            db.session.commit()
            return redirect(url_for("dashboard"))
    return render_template("choose_club.html", clubs=CLUBS)

@app.route("/dashboard")
@login_required
def dashboard():
    save = current_save()
    if not save:
        return redirect(url_for("choose_club"))
    return render_template("dashboard.html", data=get_dashboard(save.state), username=current_user.username)

@app.route("/squad")
@login_required
def squad():
    save = current_save()
    if not save:
        return redirect(url_for("choose_club"))
    return render_template("squad.html", players=get_squad(save.state))

@app.post("/play-match")
@login_required
def play_match():
    save = current_save()
    if not save:
        return redirect(url_for("choose_club"))
    # Match simulation is the next gameplay module; this starter route is deliberately safe.
    flash("Khung mô phỏng trận đấu đã sẵn sàng. Bước tiếp theo sẽ bổ sung chiến thuật và kết quả.")
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    app.run(debug=True)
