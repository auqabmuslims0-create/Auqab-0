from database import db
from models import (
    User, Order, OrderStatusHistory, Subscription, ChatMessage,
    Store, Product, Reel, ReelReaction, ReelComment, CartItem,
    Favorite, Review, ProductComment, ProductReaction,
    Notification, PushSubscription, Payment, UserActivity,
)
from shared.repositories.user_repository import UserRepository
from werkzeug.security import generate_password_hash
from shared.utils import is_strong_password, delete_local_file
import secrets


class UserService:

    @staticmethod
    def toggle_user_status(user_id, admin_user_id=None):
        target = UserRepository.get_by_id(user_id)
        if not target:
            raise ValueError('المستخدم غير موجود')
        if admin_user_id and target.id == admin_user_id:
            return False, 'لا يمكنك حظر نفسك', None

        if target.role == 'admin' and target.is_active:
            active_admins = UserRepository.get_active_admins_count()
            if active_admins <= 1:
                return False, 'لا يمكنك حظر آخر مسؤول نشط', None

        UserRepository.toggle_active(target)
        db.session.commit()
        return True, f'تم تحديث حالة المستخدم {target.username}', target

    @staticmethod
    def delete_user_fully(user_id, admin_user_id=None):
        """
        حذف المستخدم مع كل بياناته المرتبطة.
        يتعامل يدوياً مع العلاقات التي لا تدعم cascade:
          - ChatMessage (sender/receiver)
          - OrderStatusHistory.changed_by
          - Order (customer_id, delivery_person_id)
          - Subscription (user_id)
          - UserActivity (user_id هو PK — يجب الحذف لا NULL)
          - جداول أمنية إن وُجدت (LoginAttempt, PasswordReset...)
        """
        target = UserRepository.get_by_id(user_id)
        if not target:
            return False, 'المستخدم غير موجود'
        if admin_user_id and target.id == admin_user_id:
            return False, 'لا يمكنك حذف حسابك الحالي'
        if target.role == 'admin' and target.is_active:
            active_admins = UserRepository.get_active_admins_count()
            if active_admins <= 1:
                return False, 'لا يمكن حذف آخر مدير نشط'

        try:
            # ===== 1. تنظيف ملفات Cloudinary (لا يُفشل الحذف عند الخطأ) =====
            try:
                if target.avatar:
                    delete_local_file(target.avatar)
                for store in list(target.stores or []):
                    for product in list(store.products or []):
                        if product.images:
                            for img in product.images.split(','):
                                img = img.strip()
                                if img:
                                    delete_local_file(img)
                        if product.video:
                            delete_local_file(product.video)
                    if store.logo_url:
                        delete_local_file(store.logo_url)
            except Exception:
                pass

            # ===== 2. تنظيف العلاقات التي لا تدعم cascade =====

            # 2a) ChatMessage: حذف رسائل المستخدم كمرسل أو مستقبل
            ChatMessage.query.filter(
                (ChatMessage.sender_id == target.id) |
                (ChatMessage.receiver_id == target.id)
            ).delete(synchronize_session=False)

            # 2b) OrderStatusHistory.changed_by → NULL (نُبقي التاريخ)
            OrderStatusHistory.query.filter_by(changed_by=target.id).update(
                {'changed_by': None}, synchronize_session=False
            )

            # 2c) Subscription.user_id → NULL (nullable في الموديل)
            Subscription.query.filter_by(user_id=target.id).update(
                {'user_id': None}, synchronize_session=False
            )

            # 2d) Order.delivery_person_id → NULL
            Order.query.filter_by(delivery_person_id=target.id).update(
                {'delivery_person_id': None}, synchronize_session=False
            )

            # 2e) Order as customer → حذف كامل (customer_id NOT NULL)
            #     cascade على Order يحذف: OrderItem, Payment, OrderStatusHistory
            customer_orders = Order.query.filter_by(customer_id=target.id).all()
            for order in customer_orders:
                db.session.delete(order)

            # 2f) UserActivity — user_id هو PK، يجب الحذف لا NULL
            UserActivity.query.filter_by(user_id=target.id).delete(
                synchronize_session=False
            )

            # 2g) جداول أمنية إن وُجدت (احتياطي)
            try:
                import models.security as sec
                for Model in (getattr(sec, 'LoginAttempt', None),
                              getattr(sec, 'PasswordReset', None),
                              getattr(sec, 'PasswordResetAttempt', None)):
                    if Model is None:
                        continue
                    if hasattr(Model, 'user_id'):
                        Model.query.filter_by(user_id=target.id).delete(
                            synchronize_session=False
                        )
            except Exception:
                pass

            db.session.flush()

            # ===== 3. حذف المستخدم (cascade يتولى: stores, products, reels,
            #         favorites, reviews, notifications, cart, payments,
            #         push_subscriptions, reactions, comments) =====
            UserRepository.delete(target)
            db.session.commit()

            return True, 'تم حذف المستخدم وجميع بياناته بنجاح'

        except Exception as e:
            db.session.rollback()
            err_type = type(e).__name__
            err_msg = str(e).split('\n')[0][:200]
            return False, f'فشل الحذف [{err_type}]: {err_msg}'

    @staticmethod
    def reset_password(user_id):
        target = UserRepository.get_by_id(user_id)
        if not target:
            return False, 'المستخدم غير موجود', None
        while True:
            temp_password = 'Aa1!' + secrets.token_urlsafe(6)
            strong, _ = is_strong_password(temp_password)
            if strong:
                break
        target.password_hash = generate_password_hash(temp_password)
        db.session.commit()
        return True, f'تم إعادة تعيين كلمة مرور المستخدم {target.username}', temp_password
