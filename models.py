from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import JSON, UniqueConstraint

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    is_admin = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    last_seen_at = db.Column(db.DateTime, nullable=True, index=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class GameSave(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    state = db.Column(JSON, nullable=False)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())


class FriendRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    __table_args__ = (UniqueConstraint("sender_id", "receiver_id", name="uq_friend_request_pair"),)

class Friendship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_low_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    user_high_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    __table_args__ = (UniqueConstraint("user_low_id", "user_high_id", name="uq_friendship_pair"),)

class FriendlyChallenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False, default="pending")
    result_json = db.Column(JSON, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
