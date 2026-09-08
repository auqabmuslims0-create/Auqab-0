from flask import current_app
from database import db
from models import User, Notification
from shared.repositories.notification_repository import NotificationRepository
from shared.time_utils import current_time
import json
import threading

class NotificationService:
    # الأنواع
    TYPE_INFO = 'info'
    TYPE_ORDER = 'order'
    TYPE_SUBSCRIPTION = 'subscription'
    TYPE_DELIVERY = 'delivery'
    TYPE_MESSAGE = 'message'
    TYPE_ALERT = 'alert'
    TYPE_STORE_FOLLOW = 'store_follow'
    TYPE_NEW_PRODUCT = 'new_product'
    TYPE_NEW_OFFER = 'new_offer'
    TYPE_REEL = 'reel'

    # الأولويات
    PRIORITY_NORMAL = 'normal'
    PRIORITY_IMPORTANT = 'important'
    PRIORITY_URGENT = 'urgent'

    @staticmethod
    def _send_push_async(app, user_id, notif):
        with app.app_context():
            try:
                from shared.services.push_service import send_to_user as push_send_to_user
                push_send_to_user(user_id, notif)
            except Exception as e:
                app.logger.error(f"Async push failed for notification {notif.id}: {e}")

    @staticmethod
    def _create_notification(user_id, message, title=None, link=None, type_=None,
                             priority=None, icon=None, extra_data=None, expires_at=None,
                             entity_type=None, entity_id=None):
        """إنشاء كائن Notification وإضافته للجلسة دون commit فوري."""
        if not user_id:
            return None
        notif = NotificationRepository.create({
            'user_id': user_id,
            'title': title,
            'message': message,
            'link': link,
            'type': type_ or NotificationService.TYPE_INFO,
            'priority': priority or NotificationService.PRIORITY_NORMAL,
            'icon': icon,
            'extra_data': json.dumps(extra_data) if extra_data else None,
            'is_read': False,
            'expires_at': expires_at,
            'entity_type': entity_type,
            'entity_id': entity_id
        })
        return notif

    @staticmethod
    def send_to_user(user_id, message, title=None, link=None, type_=None, priority=None, icon=None,
                     extra_data=None, send_push=True, expires_at=None,
                     entity_type=None, entity_id=None, commit=True):
        """إرسال إشعار لمستخدم واحد. يمكن التحكم في commit لتجميع الإرسالات."""
        if not user_id:
            return None
        notif = NotificationService._create_notification(
            user_id, message, title=title, link=link, type_=type_, priority=priority,
            icon=icon, extra_data=extra_data, expires_at=expires_at,
            entity_type=entity_type, entity_id=entity_id
        )
        if not notif:
            return None

        if commit:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise

        if send_push:
            app = current_app._get_current_object()
            thread = threading.Thread(target=NotificationService._send_push_async, args=(app, user_id, notif))
            thread.daemon = True
            thread.start()
        return notif

    @staticmethod
    def _send_to_many(user_ids, message, title=None, link=None, type_=None, priority=None,
                      icon=None, extra_data=None, send_push=True, expires_at=None,
                      entity_type=None, entity_id=None):
        """إرسال إشعار لمجموعة مستخدمين مع تجميع commit."""
        notifs = []
        for uid in set(user_ids):
            notif = NotificationService._create_notification(
                uid, message, title=title, link=link, type_=type_, priority=priority,
                icon=icon, extra_data=extra_data, expires_at=expires_at,
                entity_type=entity_type, entity_id=entity_id
            )
            if notif:
                notifs.append(notif)
        if notifs:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
            if send_push:
                app = current_app._get_current_object()
                for notif in notifs:
                    thread = threading.Thread(target=NotificationService._send_push_async,
                                              args=(app, notif.user_id, notif))
                    thread.daemon = True
                    thread.start()
        return notifs

    @staticmethod
    def send_to_store_owner(store, message, title=None, link=None, type_=None, priority=None, icon=None,
                            extra_data=None, send_push=True, expires_at=None,
                            entity_type=None, entity_id=None):
        if store and store.owner_id:
            return NotificationService.send_to_user(
                store.owner_id, message, title=title, link=link,
                type_=type_ or NotificationService.TYPE_ORDER,
                priority=priority, icon=icon, extra_data=extra_data,
                send_push=send_push, expires_at=expires_at,
                entity_type=entity_type, entity_id=entity_id
            )
        return None

    @staticmethod
    def send_to_customer(order, message, title=None, link=None, type_=None, priority=None, icon=None,
                         extra_data=None, send_push=True, expires_at=None,
                         entity_type=None, entity_id=None):
        if order and order.customer_id:
            return NotificationService.send_to_user(
                order.customer_id, message, title=title, link=link,
                type_=type_ or NotificationService.TYPE_ORDER,
                priority=priority, icon=icon, extra_data=extra_data,
                send_push=send_push, expires_at=expires_at,
                entity_type=entity_type, entity_id=entity_id
            )
        return None

    @staticmethod
    def send_to_delivery_person(user_id, message, title=None, link=None, type_=None, priority=None, icon=None,
                                extra_data=None, send_push=True, expires_at=None,
                                entity_type=None, entity_id=None):
        if user_id:
            return NotificationService.send_to_user(
                user_id, message, title=title, link=link,
                type_=type_ or NotificationService.TYPE_DELIVERY,
                priority=priority, icon=icon, extra_data=extra_data,
                send_push=send_push, expires_at=expires_at,
                entity_type=entity_type, entity_id=entity_id
            )
        return None

    @staticmethod
    def send_to_admins(message, title=None, link=None, type_=None, priority=None, icon=None,
                       extra_data=None, exclude_user_id=None, send_push=True, expires_at=None,
                       entity_type=None, entity_id=None):
        admins = User.query.filter_by(role='admin', is_active=True).all()
        admin_ids = [a.id for a in admins if a.id != exclude_user_id]
        return NotificationService._send_to_many(
            admin_ids, message, title=title, link=link, type_=type_ or NotificationService.TYPE_ALERT,
            priority=priority, icon=icon, extra_data=extra_data,
            send_push=send_push, expires_at=expires_at,
            entity_type=entity_type, entity_id=entity_id
        )

    @staticmethod
    def send_to_role(role, message, title=None, link=None, type_=None, priority=None, icon=None,
                     extra_data=None, send_push=True, expires_at=None,
                     entity_type=None, entity_id=None):
        users = User.query.filter_by(role=role, is_active=True).all()
        user_ids = [u.id for u in users]
        return NotificationService._send_to_many(
            user_ids, message, title=title, link=link, type_=type_ or NotificationService.TYPE_INFO,
            priority=priority, icon=icon, extra_data=extra_data,
            send_push=send_push, expires_at=expires_at,
            entity_type=entity_type, entity_id=entity_id
        )

    @staticmethod
    def send_to_all_users(message, title=None, link=None, type_=None, priority=None, icon=None,
                          extra_data=None, send_push=True, expires_at=None,
                          entity_type=None, entity_id=None):
        users = User.query.filter_by(is_active=True).all()
        user_ids = [u.id for u in users]
        return NotificationService._send_to_many(
            user_ids, message, title=title, link=link, type_=type_ or NotificationService.TYPE_INFO,
            priority=priority, icon=icon, extra_data=extra_data,
            send_push=send_push, expires_at=expires_at,
            entity_type=entity_type, entity_id=entity_id
        )

    @staticmethod
    def send_to_followers(store, message, title=None, link=None, type_=None, priority=None, icon=None,
                          extra_data=None, send_push=True, expires_at=None,
                          entity_type=None, entity_id=None):
        """إرسال إشعار لمتابعي متجر معين. يفترض وجود علاقة Follow لاحقاً."""
        # ملاحظة: لم يتم تنفيذ نموذج Follow بعد، سنضع استعلامًا افتراضيًا فارغًا
        # TODO: عند إضافة نموذج Follow، قم بجلب user_ids من المتابعين
        follower_ids = []  # تعديل لاحق بعد نظام المتابعة
        return NotificationService._send_to_many(
            follower_ids, message, title=title, link=link,
            type_=type_ or NotificationService.TYPE_STORE_FOLLOW,
            priority=priority, icon=icon, extra_data=extra_data,
            send_push=send_push, expires_at=expires_at,
            entity_type=entity_type, entity_id=entity_id
        )

    # ========== دوال مساعدة للأنظمة الأخرى ==========
    @staticmethod
    def notify_order_status_changed(order, new_status):
        """إرسال إشعار للعميل وصاحب المتجر عند تغيير حالة الطلب."""
        # للعميل
        message_customer = f"تم تحديث حالة طلبك إلى: {new_status}"
        NotificationService.send_to_customer(
            order, message_customer,
            title="تحديث حالة الطلب",
            type_=NotificationService.TYPE_ORDER,
            link=f"/customer/orders/{order.id}",
            entity_type='order', entity_id=order.id
        )
        # لصاحب المتجر
        store = order.store
        if store:
            message_owner = f"تغيرت حالة الطلب {order.id} إلى {new_status}"
            NotificationService.send_to_store_owner(
                store, message_owner,
                title="تحديث حالة طلب",
                type_=NotificationService.TYPE_ORDER,
                link=f"/store/orders/{order.id}",
                entity_type='order', entity_id=order.id
            )

    @staticmethod
    def notify_new_order(order):
        """إشعار صاحب المتجر بوجود طلب جديد."""
        store = order.store
        if store:
            NotificationService.send_to_store_owner(
                store, f"لديك طلب جديد رقم {order.id}",
                title="طلب جديد",
                type_=NotificationService.TYPE_ORDER,
                link=f"/store/orders/{order.id}",
                entity_type='order', entity_id=order.id
            )

    @staticmethod
    def notify_new_product(product):
        """إشعار متابعي المتجر بإضافة منتج جديد."""
        if product and product.store:
            NotificationService.send_to_followers(
                product.store,
                f"أُضيف منتج جديد: {product.name}",
                title="منتج جديد",
                type_=NotificationService.TYPE_NEW_PRODUCT,
                link=f"/stores/{product.store.id}/products/{product.id}",
                entity_type='product', entity_id=product.id
            )

    @staticmethod
    def notify_new_offer(product):
        """إشعار متابعي المتجر بوجود عرض جديد."""
        if product and product.store and product.is_offer:
            NotificationService.send_to_followers(
                product.store,
                f"عرض جديد: {product.name}",
                title="عرض جديد",
                type_=NotificationService.TYPE_NEW_OFFER,
                link=f"/stores/{product.store.id}/products/{product.id}",
                entity_type='product', entity_id=product.id
            )

    @staticmethod
    def notify_new_reel(reel):
        """إشعار متابعي المتجر بإضافة ريل جديد."""
        if reel and reel.store:
            NotificationService.send_to_followers(
                reel.store,
                f"ريل جديد من {reel.store.name}",
                title="ريل جديد",
                type_=NotificationService.TYPE_REEL,
                link=f"/reels/{reel.id}",
                entity_type='reel', entity_id=reel.id
            )

    # ========== إدارة القراءة والحذف ==========
    @staticmethod
    def mark_as_read(notification_id, user_id=None):
        notif = NotificationRepository.get_by_id(notification_id)
        if not notif:
            return False
        if user_id and notif.user_id != user_id:
            return False
        NotificationRepository.mark_as_read(notif)
        db.session.commit()
        return True

    @staticmethod
    def mark_all_as_read(user_id):
        NotificationRepository.mark_all_as_read(user_id)
        db.session.commit()
        return True

    @staticmethod
    def delete(notification_id, user_id=None):
        notif = NotificationRepository.get_by_id(notification_id)
        if not notif:
            return False
        if user_id and notif.user_id != user_id:
            return False
        NotificationRepository.delete(notif)
        db.session.commit()
        return True

    @staticmethod
    def delete_all_read(user_id):
        NotificationRepository.delete_all_read(user_id)
        db.session.commit()
        return True

    @staticmethod
    def get_unread_count(user_id):
        return NotificationRepository.get_unread_count(user_id)

    @staticmethod
    def get_user_notifications(user_id, limit=20, offset=0, filter_type=None, filter_read=None):
        return NotificationRepository.get_user_notifications(
            user_id=user_id, limit=limit, offset=offset, filter_type=filter_type, filter_read=filter_read
        )

    @staticmethod
    def delete_expired():
        NotificationRepository.delete_expired()
        db.session.commit()
