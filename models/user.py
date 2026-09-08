from datetime import datetime
from database import db
from shared.time_utils import current_time

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=True)
    avatar = db.Column(db.String(300), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    dark_mode = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(20), nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True)
    shift_start_time = db.Column(db.Time, nullable=True)
    shift_end_time = db.Column(db.Time, nullable=True)
    max_active_orders = db.Column(db.Integer, default=3)
    is_available = db.Column(db.Boolean, default=True)
    public_id = db.Column(db.String(20), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=current_time)

    stores = db.relationship('Store', back_populates='owner', cascade="all, delete-orphan")
    orders = db.relationship('Order', back_populates='customer', foreign_keys='Order.customer_id')
    reviews = db.relationship('Review', back_populates='user', cascade="all, delete-orphan")
    favorites = db.relationship('Favorite', back_populates='user', cascade="all, delete-orphan")
    notifications = db.relationship('Notification', back_populates='user', cascade="all, delete-orphan")
    subscriptions = db.relationship('Subscription', back_populates='user', foreign_keys='Subscription.user_id')
    product_comments = db.relationship('ProductComment', back_populates='user', cascade="all, delete-orphan")
    delivery_orders = db.relationship('Order', back_populates='delivery_person', foreign_keys='Order.delivery_person_id')
    cart_items = db.relationship('CartItem', back_populates='user', cascade="all, delete-orphan")
    payments = db.relationship('Payment', back_populates='user', cascade="all, delete-orphan")
    push_subscriptions = db.relationship('PushSubscription', back_populates='user', cascade="all, delete-orphan")
    reels_reactions = db.relationship('ReelReaction', back_populates='user', cascade="all, delete-orphan")
    reels_comments = db.relationship('ReelComment', back_populates='user', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<User {self.username}>'
