from database import db
from models import Notification

class NotificationRepository:
    @staticmethod
    def create(notification_data):
        notif = Notification(**notification_data)
        db.session.add(notif)
        return notif

    @staticmethod
    def bulk_create(notifications_data):
        """إنشاء عدة إشعارات دفعة واحدة."""
        notifs = [Notification(**data) for data in notifications_data]
        db.session.add_all(notifs)
        return notifs

    @staticmethod
    def get_by_id(notification_id):
        return db.session.get(Notification, notification_id)

    @staticmethod
    def mark_as_read(notification):
        notification.is_read = True
        notification.read_at = db.func.now()
        db.session.add(notification)

    @staticmethod
    def mark_all_as_read(user_id):
        Notification.query.filter_by(user_id=user_id, is_read=False).update(
            {'is_read': True, 'read_at': db.func.now()}
        )

    @staticmethod
    def delete(notification):
        db.session.delete(notification)

    @staticmethod
    def delete_all_read(user_id):
        Notification.query.filter_by(user_id=user_id, is_read=True).delete()

    @staticmethod
    def delete_selected(user_id, ids):
        Notification.query.filter(
            Notification.id.in_(ids),
            Notification.user_id == user_id
        ).delete(synchronize_session=False)

    @staticmethod
    def get_unread_count(user_id):
        return Notification.query.filter_by(user_id=user_id, is_read=False).count()

    @staticmethod
    def get_user_notifications(user_id, limit=20, offset=0, filter_type=None, filter_read=None):
        query = Notification.query.filter(Notification.user_id == user_id)
        if filter_type:
            query = query.filter(Notification.type == filter_type)
        if filter_read is not None:
            if filter_read in ('true', True):
                query = query.filter(Notification.is_read == True)
            elif filter_read in ('false', False):
                query = query.filter(Notification.is_read == False)
        return query.order_by(Notification.created_at.desc()).offset(offset).limit(limit).all()

    @staticmethod
    def count_user_notifications(user_id, filter_type=None, filter_read=None):
        query = Notification.query.filter(Notification.user_id == user_id)
        if filter_type:
            query = query.filter(Notification.type == filter_type)
        if filter_read is not None:
            if filter_read in ('true', True):
                query = query.filter(Notification.is_read == True)
            elif filter_read in ('false', False):
                query = query.filter(Notification.is_read == False)
        return query.count()

    @staticmethod
    def delete_expired():
        Notification.query.filter(
            Notification.expires_at.isnot(None),
            Notification.expires_at < db.func.now()
        ).delete(synchronize_session=False)

    @staticmethod
    def get_notifications_by_entity(entity_type, entity_id, user_id=None):
        """استعلام عن إشعارات مرتبطة بكيان معين."""
        query = Notification.query.filter_by(entity_type=entity_type, entity_id=entity_id)
        if user_id:
            query = query.filter(Notification.user_id == user_id)
        return query.all()
