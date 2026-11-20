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
    settings_json = db.Column(JSON, nullable=False, default=dict)

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
class PlayerMarketListing(db.Model):
    __tablename__ = "player_market_listing"

    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True
    )
    buyer_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
        index=True
    )
    player_name = db.Column(
        db.String(100),
        nullable=False,
        index=True
    )
    player_data = db.Column(JSON, nullable=False)
    player_group = db.Column(
        db.String(16),
        nullable=False,
        default="bench"
    )
    asking_price = db.Column(db.Float, nullable=False)
    status = db.Column(
        db.String(16),
        nullable=False,
        default="active",
        index=True
    )
    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now()
    )
    sold_at = db.Column(db.DateTime, nullable=True)


class A1CupSeason(db.Model):
    __tablename__ = "a1_cup_season"
    id = db.Column(db.Integer, primary_key=True)
    season_number = db.Column(db.Integer, nullable=False, unique=True, index=True)
    name = db.Column(db.String(80), nullable=False, default="Academic League (A1 Cup)")
    start_at = db.Column(db.DateTime, nullable=False, index=True)
    teams = db.Column(JSON, nullable=False)
    matches = db.Column(JSON, nullable=False)
    champion_user_id = db.Column(db.Integer, nullable=True)
    runner_up_user_id = db.Column(db.Integer, nullable=True)
    third_user_id = db.Column(db.Integer, nullable=True)
    prizes_awarded = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class SupportMessage(db.Model):
    __tablename__ = "support_message"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    user = db.relationship("User")
    category = db.Column(db.String(32), nullable=False, default="Góp ý")
    subject = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Mới")
    admin_seen = db.Column(db.Boolean, nullable=False, default=False)
    admin_reply = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), index=True)
    replied_at = db.Column(db.DateTime, nullable=True)


class GiftCode(db.Model):
    __tablename__ = "gift_code"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    pc_millions = db.Column(db.Float, nullable=False, default=0)
    pg = db.Column(db.Integer, nullable=False, default=0)
    protection_cards = db.Column(db.Integer, nullable=False, default=0)
    max_redemptions = db.Column(db.Integer, nullable=False, default=0)  # 0 = unlimited
    redemption_count = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class GiftCodeRedemption(db.Model):
    __tablename__ = "gift_code_redemption"
    id = db.Column(db.Integer, primary_key=True)
    gift_code_id = db.Column(db.Integer, db.ForeignKey("gift_code.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    redeemed_at = db.Column(db.DateTime, server_default=db.func.now())
    __table_args__ = (UniqueConstraint("gift_code_id", "user_id", name="uq_gift_code_user"),)
