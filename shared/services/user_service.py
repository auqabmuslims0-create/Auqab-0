from database import db
from models import (
    User, Order, OrderStatusHistory, Subscription, ChatMessage,
    Store, Product, Reel, ReelReaction, CartItem,
    Favorite, Review, ProductComment, ProductReaction,
    Notification, PushSubscription, Payment, UserActivity,
    LoginAttempt, PasswordReset, PasswordResetAttempt,
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

        ملاحظات cascade:
          - User.stores: cascade="all, delete-orphan"
          - Store.products/categories/cart_items/reels/favorites: cascade=all (m-2 B2)
          - Store.orders/payments/subscriptions: بلا cascade → تُحذف يدوياً هنا
          - Order.items/payments/status_history: cascade=all
          - Product.reviews/favorites/reactions/comments/cart_items/reels: cascade=all

        ترتيب الحذف مهم:
          1. دفعات اشتراكات متاجر المستخدم (قبل الاشتراكات)
          2. اشتراكات متاجر المستخدم
          3. دفعات المتاجر مباشرة
          4. الطلبات (زبون + متاجر)
          5. باقي العلاقات الخاصة
          6. حذف المستخدم (cascade)
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
            # ===== 1. تنظيف ملفات الوسائط =====
            try:
                if target.avatar:
                    delete_local_file(target.avatar)
                for store in list(target.stores or []):
                    if store.logo_url:
                        delete_local_file(store.logo_url)
                    for product in list(store.products or []):
                        if product.images:
                            for img in product.images.split(','):
                                img = img.strip()
                                if img:
                                    delete_local_file(img)
                        if product.video:
                            delete_local_file(product.video)
            except Exception:
                pass

            # ===== 2. معالجة العلاقات الخاصة =====

            # 2a) ChatMessage (sender/receiver) → DELETE
            ChatMessage.query.filter(
                (ChatMessage.sender_id == target.id) |
                (ChatMessage.receiver_id == target.id)
            ).delete(synchronize_session=False)

            # 2b) OrderStatusHistory.changed_by → NULL
            OrderStatusHistory.query.filter_by(changed_by=target.id).update(
                {'changed_by': None}, synchronize_session=False
            )

            # 2c) Subscription.user_id → NULL
            Subscription.query.filter_by(user_id=target.id).update(
                {'user_id': None}, synchronize_session=False
            )

            # 2d) Order.delivery_person_id → NULL
            Order.query.filter_by(delivery_person_id=target.id).update(
                {'delivery_person_id': None}, synchronize_session=False
            )

            # 2e) طلبات المستخدم كزبون → DELETE
            customer_orders = Order.query.filter_by(customer_id=target.id).all()
            for order in customer_orders:
                db.session.delete(order)

            # 2f) ما يخص متاجر المستخدم (سيتم حذف المتاجر عبر cascade على User.stores)
            #     ترتيب مهم: payments أولاً ثم subscriptions
            for store in list(target.stores or []):
                # 2f-1) دفعات المتجر مباشرة
                Payment.query.filter_by(store_id=store.id).delete(synchronize_session=False)

                # 2f-2) دفعات اشتراكات المتجر (احتياطي)
                store_sub_ids = [
                    s_id for (s_id,) in db.session.query(Subscription.id)
                    .filter_by(store_id=store.id).all()
                ]
                if store_sub_ids:
                    Payment.query.filter(
                        Payment.subscription_id.in_(store_sub_ids)
                    ).delete(synchronize_session=False)

                # 2f-3) اشتراكات المتجر
                Subscription.query.filter_by(store_id=store.id).delete(synchronize_session=False)

                # 2f-4) طلبات المتجر
                store_orders = Order.query.filter_by(store_id=store.id).all()
                for order in store_orders:
                    db.session.delete(order)

            # 2g) UserActivity (PK) → DELETE
            UserActivity.query.filter_by(user_id=target.id).delete(
                synchronize_session=False
            )

            # 2h) PasswordReset (NOT NULL) → DELETE
            PasswordReset.query.filter_by(user_id=target.id).delete(
                synchronize_session=False
            )

            # 2i) LoginAttempt.user_id → NULL
            LoginAttempt.query.filter_by(user_id=target.id).update(
                {'user_id': None}, synchronize_session=False
            )

            db.session.flush()

            # ===== 3. حذف المستخدم (cascade: stores → products/categories/reels/
            #         cart_items/favorites, favorites, reviews, notifications,
            #         cart, push_subscriptions, reactions, comments) =====
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
