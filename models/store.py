from database import db
from sqlalchemy import CheckConstraint
from shared.time_utils import current_time

class Store(db.Model):
    __tablename__ = 'stores'
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    logo_url = db.Column(db.String(300), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(200), nullable=True)
    working_hours = db.Column(db.String(100), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    has_delivery = db.Column(db.Boolean, default=False)
    subscription_status = db.Column(db.String(20), default='pending', index=True)
    subscription_expiry = db.Column(db.DateTime, nullable=True)
    pending_deletion_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=current_time)

    __table_args__ = (
        CheckConstraint(
            "subscription_status IN ('pending', 'active', 'suspended', 'cancelled', 'expired')",
            name='ck_store_subscription_status_valid'
        ),
    )

    owner = db.relationship('User', back_populates='stores')
    products = db.relationship('Product', back_populates='store', cascade="all, delete-orphan")
    orders = db.relationship('Order', back_populates='store')
    categories = db.relationship('Category', back_populates='store', cascade="all, delete-orphan")
    subscriptions = db.relationship('Subscription', back_populates='store', foreign_keys='Subscription.store_id')
    cart_items = db.relationship('CartItem', back_populates='store', cascade="all, delete-orphan")
    payments = db.relationship('Payment', back_populates='store')
    reels = db.relationship('Reel', back_populates='store', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Store {self.name}>'

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=True, index=True)

    parent = db.relationship('Category', remote_side=[id], back_populates='children')
    children = db.relationship('Category', back_populates='parent')
    products = db.relationship('Product', back_populates='category')
    store = db.relationship('Store', back_populates='categories')

    def __repr__(self):
        return f'<Category {self.name}>'
