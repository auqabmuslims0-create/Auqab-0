from database import db
from sqlalchemy import CheckConstraint
from shared.time_utils import current_time

class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True, index=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=True, index=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=True, index=True)
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(30), nullable=False, default='cash')
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    reference = db.Column(db.String(100), nullable=True)
    proof_image = db.Column(db.String(300), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=current_time, index=True)
    updated_at = db.Column(db.DateTime, default=current_time, onupdate=current_time)

    __table_args__ = (
        CheckConstraint('amount >= 0', name='ck_payment_amount_non_negative'),
        CheckConstraint("status IN ('pending', 'paid', 'failed', 'refunded')", name='ck_payment_status_valid'),
        CheckConstraint(
            "method IN ('cash', 'wallet', 'bank_transfer', 'manual_delivery')",
            name='ck_payment_method_valid'
        ),
        CheckConstraint(
            '(order_id IS NOT NULL) OR (store_id IS NOT NULL) OR (subscription_id IS NOT NULL)',
            name='ck_payment_has_reference'
        ),
    )

    user = db.relationship('User', back_populates='payments')
    order = db.relationship('Order', back_populates='payments')
    store = db.relationship('Store', back_populates='payments')
    subscription = db.relationship('Subscription', back_populates='payments')

    def __repr__(self):
        return f'<Payment {self.id} - {self.amount}>'
