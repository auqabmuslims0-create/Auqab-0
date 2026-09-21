from database import db
from models import Store, Order, Product, Category, Subscription, Payment, User
from shared.repositories.store_repository import StoreRepository
from shared.services.notification_service import NotificationService
from shared.utils import is_store_active, get_setting, delete_local_file
from shared.time_utils import current_time
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class StoreService:
    @staticmethod
    def _create_admin_subscription(store, days=None):
        if days is None:
            if store.custom_subscription_duration_days is not None:
                days = int(store.custom_subscription_duration_days)
            else:
                days = int(get_setting('subscription_duration_days', 30))
        sub = Subscription(
            user_id=store.owner_id,
            store_id=store.id,
            start_date=current_time(),
            end_date=current_time() + timedelta(days=days),
            amount=0.0,
            status='paid',
            payment_method='manual_delivery',
            payment_ref=None,
            proof_image=None,
            confirmation_code=None,
            duration_days=days,
            renewal_count=0,
            expiry_notified=False
        )
        db.session.add(sub)
        db.session.flush()
        return sub

    @staticmethod
    def toggle_store_status(store_id, force_activate=False):
        store = StoreRepository.get_by_id(store_id)
        if not store:
            return False, 'المتجر غير موجود', None

        try:
            if store.subscription_status == 'active':
                store.subscription_status = 'suspended'
                action = 'تم تعليق المتجر'
            elif store.subscription_status in ['suspended', 'cancelled', 'expired']:
                if force_activate:
                    if not is_store_active(store):
                        sub = StoreService._create_admin_subscription(store)
                        store.subscription_status = 'active'
                        store.subscription_expiry = sub.end_date
                    else:
                        store.subscription_status = 'active'
                    action = 'تم تفعيل المتجر (تفعيل إداري)'
                else:
                    if not is_store_active(store):
                        return False, 'لا يمكن تفعيل المتجر لعدم وجود اشتراك ساري المفعول', store
                    store.subscription_status = 'active'
                    action = 'تم تفعيل المتجر'
            else:
                return False, 'لا يمكن تنفيذ الإجراء على متجر بحالة "قيد الانتظار"', store

            db.session.commit()

            if store.owner_id:
                owner = db.session.get(User, store.owner_id)
                if owner:
                    NotificationService.send_to_user(
                        user_id=owner.id,
                        title='تحديث حالة المتجر',
                        message=f'قام المدير بتغيير حالة متجرك "{store.name}" إلى {store.subscription_status}',
                        link=f'/store/{store.id}',
                        type_=NotificationService.TYPE_ALERT,
                        priority=NotificationService.PRIORITY_IMPORTANT
                    )
                    db.session.commit()
            return True, action, store
        except Exception as e:
            db.session.rollback()
            logger.error(f'خطأ في تغيير حالة المتجر {store_id}: {str(e)}')
            return False, 'حدث خطأ غير متوقع أثناء تنفيذ الإجراء', store

    @staticmethod
    def delete_store(store_id):
        """
        حذف المتجر وكل بياناته.

        الاعتماد على cascade:
          - Store.products       : cascade → يحذف المنتجات وتوابعها
          - Store.categories     : cascade → يحذف التصنيفات
          - Store.cart_items     : cascade
          - Store.reels          : cascade
          - Store.favorites      : cascade (m-2 B2) → يحذف مفضلات المتجر
          - Order.items/payments/status_history: cascade

        الحذف اليدوي المطلوب (بلا cascade على Store):
          - ملفات الوسائط (القرص)
          - Store.orders          : بلا cascade (store_id NOT NULL)
          - Store.payments        : بلا cascade
          - Subscription.payments : بلا cascade (يجب حذف الدفعات قبل الاشتراكات)

        ⚠️ ترتيب الحذف مهم في PostgreSQL:
          payments المرتبطة بـ subscription_id يجب حذفها قبل subscriptions.
        """
        store = StoreRepository.get_by_id(store_id)
        if not store:
            return False, 'المتجر غير موجود'
        try:
            # 1) حذف ملفات الوسائط
            if store.logo_url:
                delete_local_file(store.logo_url)
            for product in (store.products or []):
                if product.main_image:
                    delete_local_file(product.main_image)
                if product.sub_images:
                    for img_name in product.sub_images.split(','):
                        img_name = img_name.strip()
                        if img_name:
                            delete_local_file(img_name)
                if product.video:
                    delete_local_file(product.video)

            # 2) حذف الطلبات (cascade على Order يتولى items/payments/history)
            orders = Order.query.filter_by(store_id=store.id).all()
            for order in orders:
                db.session.delete(order)

            db.session.flush()

            # 3) حذف الدفعات المرتبطة بالمتجر مباشرة
            Payment.query.filter_by(store_id=store.id).delete(synchronize_session=False)

            # 4) حذف دفعات اشتراكات المتجر (احتياطي)
            store_sub_ids = [
                s_id for (s_id,) in db.session.query(Subscription.id)
                .filter_by(store_id=store.id).all()
            ]
            if store_sub_ids:
                Payment.query.filter(
                    Payment.subscription_id.in_(store_sub_ids)
                ).delete(synchronize_session=False)

            db.session.flush()

            # 5) حذف الاشتراكات
            Subscription.query.filter_by(store_id=store.id).delete(synchronize_session=False)

            # 6) حذف المتجر — cascade يتولى الباقي
            StoreRepository.delete(store)
            db.session.commit()
            return True, 'تم حذف المتجر بنجاح'
        except Exception as e:
            db.session.rollback()
            logger.error(f'خطأ في حذف المتجر {store_id}: {str(e)}')
            return False, 'حدث خطأ أثناء حذف المتجر'

    @staticmethod
    def admin_delete_store(store_id):
        """
        حذف نهائي للمتجر من لوحة المدير.

        - يحفظ معلومات المتجر/المالك قبل الحذف (للإشعار).
        - يستدعي delete_store() القائمة (Hard Delete شامل).
        - يرسل إشعاراً للمالك بعد الحذف (best-effort — فشل الإشعار لا يفشل الحذف).
        - لا يمس بيانات المستخدم أو متاجره الأخرى إطلاقاً.
        """
        store = StoreRepository.get_by_id(store_id)
        if not store:
            return False, 'المتجر غير موجود'

        store_name = store.name
        owner_id = store.owner_id

        success, msg = StoreService.delete_store(store_id)
        if not success:
            return False, msg

        if owner_id:
            try:
                NotificationService.send_to_user(
                    user_id=owner_id,
                    title='تم حذف متجرك',
                    message=f'قام المدير بحذف متجر "{store_name}" وجميع بياناته. هذا الإجراء نهائي ولا يمكن التراجع عنه.',
                    link='/my_stores',
                    type_=NotificationService.TYPE_ALERT,
                    priority=NotificationService.PRIORITY_IMPORTANT
                )
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f'فشل إشعار المالك {owner_id} بعد حذف المتجر {store_id}: {str(e)}')

        return True, f'تم حذف المتجر "{store_name}" نهائياً'
