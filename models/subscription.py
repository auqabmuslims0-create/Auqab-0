from database import db
from sqlalchemy import CheckConstraint, Index
from shared.time_utils import current_time

class Subscription(db.Model):
    __tablename__ = 'subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=True, index=True)
    start_date = db.Column(db.DateTime, default=current_time)
    end_date = db.Column(db.DateTime, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending', index=True)
    payment_ref = db.Column(db.String(100), nullable=True)
    proof_image = db.Column(db.String(300), nullable=True)
    payment_method = db.Column(db.String(30), default='manual_delivery')
    confirmation_code = db.Column(db.String(20), nullable=True)
    confirmation_attempts = db.Column(db.Integer, default=0)
    confirmation_expiry = db.Column(db.DateTime, nullable=True)
    expiry_notified = db.Column(db.Boolean, default=False)
    duration_days = db.Column(db.Integer, default=30)
    renewal_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=current_time)

    __table_args__ = (
        CheckConstraint('amount >= 0', name='ck_subscription_amount_non_negative'),
        CheckConstraint("status IN ('pending', 'paid', 'cancelled', 'expired', 'suspended')", name='ck_subscription_status_valid'),
        CheckConstraint('(user_id IS NOT NULL) OR (store_id IS NOT NULL)', name='ck_subscription_user_or_store'),
        CheckConstraint(
            "payment_method IN ('cash', 'wallet', 'bank_transfer', 'manual_delivery')",
            name='ck_subscription_payment_method_valid'
        ),
        Index('ix_subscription_store_status', 'store_id', 'status'),
        Index('ix_subscription_end_date', 'end_date'),
    )

    user = db.relationship('User', back_populates='subscriptions', foreign_keys=[user_id])
    store = db.relationship('Store', back_populates='subscriptions', foreign_keys=[store_id])
    payments = db.relationship('Payment', back_populates='subscription')
