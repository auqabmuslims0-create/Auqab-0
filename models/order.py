from database import db
from sqlalchemy import CheckConstraint, Index
from shared.time_utils import current_time

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False, index=True)
    delivery_person_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    status = db.Column(db.String(20), default='new', index=True)
    total = db.Column(db.Float, nullable=False)
    delivery_fee = db.Column(db.Float, default=0.0)
    delivery_code = db.Column(db.String(6), nullable=True)
    delivery_address = db.Column(db.String(200), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    is_cancelled = db.Column(db.Boolean, default=False)
    payment_method = db.Column(db.String(30), default='cash')
    created_at = db.Column(db.DateTime, default=current_time, index=True)
    delivered_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint('total >= 0', name='ck_order_total_non_negative'),
        CheckConstraint('delivery_fee >= 0', name='ck_order_delivery_fee_non_negative'),
        CheckConstraint(
            "status IN ('new', 'confirmed', 'preparing', 'ready', 'delivering', 'delivered', 'cancelled')",
            name='ck_order_status_valid'
        ),
        CheckConstraint(
            "payment_method IN ('cash', 'wallet', 'bank_transfer', 'manual_delivery')",
            name='ck_order_payment_method_valid'
        ),
        Index('ix_order_store_created', 'store_id', 'created_at'),
        Index('ix_order_customer_created', 'customer_id', 'created_at'),
        Index('ix_order_delivery_created', 'delivery_person_id', 'created_at'),
        Index('ix_order_store_status', 'store_id', 'status'),
        Index('ix_order_customer_status', 'customer_id', 'status'),
    )

    customer = db.relationship('User', back_populates='orders', foreign_keys=[customer_id])
    store = db.relationship('Store', back_populates='orders')
    delivery_person = db.relationship('User', back_populates='delivery_orders', foreign_keys=[delivery_person_id])
    items = db.relationship('OrderItem', back_populates='order', cascade="all, delete-orphan")
    payments = db.relationship('Payment', back_populates='order', cascade="all, delete-orphan")
    status_history = db.relationship('OrderStatusHistory', back_populates='order', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Order {self.id}>'

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    price = db.Column(db.Float, nullable=False)
    options_selected = db.Column(db.Text, nullable=True)

    __table_args__ = (
        CheckConstraint('quantity > 0', name='ck_orderitem_quantity_positive'),
        CheckConstraint('price >= 0', name='ck_orderitem_price_non_negative'),
    )

    order = db.relationship('Order', back_populates='items')
    product = db.relationship('Product', back_populates='order_items')

    def __repr__(self):
        return f'<OrderItem {self.product_id} x{self.quantity}>'

class OrderStatusHistory(db.Model):
    __tablename__ = 'order_status_history'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    from_status = db.Column(db.String(20), nullable=True)
    to_status = db.Column(db.String(20), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    note = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=current_time)

    order = db.relationship('Order', back_populates='status_history')
    actor = db.relationship('User', foreign_keys=[changed_by])
