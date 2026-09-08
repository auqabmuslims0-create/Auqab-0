from database import db
from sqlalchemy import Index
from shared.time_utils import current_time

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    title = db.Column(db.String(200), nullable=True)
    message = db.Column(db.String(200), nullable=False)
    link = db.Column(db.String(200), nullable=True)
    is_read = db.Column(db.Boolean, default=False, index=True)
    type = db.Column(db.String(50), default='info', index=True)
    priority = db.Column(db.String(20), default='normal')
    icon = db.Column(db.String(50), nullable=True)
    is_global = db.Column(db.Boolean, default=False)
    extra_data = db.Column(db.Text, nullable=True)
    # حقول جديدة لربط الإشعار بمصدره
    entity_type = db.Column(db.String(50), nullable=True, index=True)  # order, product, store, reel, subscription
    entity_id = db.Column(db.Integer, nullable=True, index=True)
    read_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=current_time)

    __table_args__ = (
        Index('ix_notification_user_read', 'user_id', 'is_read'),
        Index('ix_notification_user_type', 'user_id', 'type'),
        Index('ix_notification_expires', 'expires_at'),
        Index('ix_notification_entity', 'entity_type', 'entity_id'),
    )

    user = db.relationship('User', back_populates='notifications')

class PushSubscription(db.Model):
    __tablename__ = 'push_subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    endpoint = db.Column(db.Text, nullable=False, unique=True)
    p256dh = db.Column(db.String(200), nullable=False)
    auth = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=current_time)

    user = db.relationship('User', back_populates='push_subscriptions')

    def to_dict(self):
        return {
            'endpoint': self.endpoint,
            'keys': {
                'p256dh': self.p256dh,
                'auth': self.auth
            }
        }
