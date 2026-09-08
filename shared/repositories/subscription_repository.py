from database import db
from models import Subscription, Store
from sqlalchemy import func

class SubscriptionRepository:
    @staticmethod
    def get_by_id(subscription_id):
        return db.session.get(Subscription, subscription_id)

    @staticmethod
    def create(subscription_data):
        sub = Subscription(**subscription_data)
        db.session.add(sub)
        return sub

    @staticmethod
    def update(subscription):
        db.session.add(subscription)

    @staticmethod
    def get_active_subscription_for_store(store_id):
        return Subscription.query.filter_by(store_id=store_id, status='paid').filter(Subscription.end_date > db.func.now()).first()

    @staticmethod
    def get_pending_subscription_for_store(store_id):
        return Subscription.query.filter_by(store_id=store_id, status='pending').order_by(Subscription.created_at.desc()).first()

    @staticmethod
    def get_expiring_subscriptions(threshold_date):
        return Subscription.query.filter(
            Subscription.status == 'paid',
            Subscription.end_date > db.func.now(),
            Subscription.end_date <= threshold_date,
            Subscription.expiry_notified == False
        ).all()

    @staticmethod
    def get_expired_subscriptions(now):
        return Subscription.query.filter(
            Subscription.status == 'paid',
            Subscription.end_date <= now
        ).all()

    @staticmethod
    def set_expiry_notified(subscription):
        subscription.expiry_notified = True
        db.session.add(subscription)
