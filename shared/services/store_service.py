from database import db
from models import Store, Order, OrderItem, Product, Category, Subscription, Payment, Favorite
import models
from shared.repositories.store_repository import StoreRepository
from shared.repositories.notification_repository import NotificationRepository
from shared.services.notification_service import NotificationService
from shared.utils import get_upload_path, is_store_active, get_setting, delete_local_file
from shared.time_utils import current_time
from datetime import timedelta
import os
import logging

logger = logging.getLogger(__name__)

class StoreService:
    @staticmethod
    def _create_admin_subscription(store):
        duration_days = int(get_setting('subscription_duration_days', 30))
        sub = Subscription(
            user_id=store.owner_id,
            store_id=store.id,
            start_date=current_time(),
            end_date=current_time() + timedelta(days=duration_days),
            amount=0.0,
            status='paid',
            payment_method='manual_delivery',
            payment_ref=None,
            proof_image=None,
            confirmation_code=None,
            duration_days=duration_days,
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
                owner = db.session.get(models.User, store.owner_id)
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
        store = StoreRepository.get_by_id(store_id)
        if not store:
            return False, 'المتجر غير موجود'
        try:
            # حذف شعار المتجر
            if store.logo_url:
                delete_local_file(store.logo_url)

            # حذف الطلبات وعناصرها
            orders = Order.query.filter_by(store_id=store.id).all()
            for order in orders:
                OrderItem.query.filter_by(order_id=order.id).delete()
                db.session.delete(order)

            # حذف المنتجات وملفاتها
            products = Product.query.filter_by(store_id=store.id).all()
            for product in products:
                # حذف الصور
                if product.main_image:
                    delete_local_file(product.main_image)
                if product.sub_images:
                    for img_name in product.sub_images.split(','):
                        img_name = img_name.strip()
                        if img_name:
                            delete_local_file(img_name)
                if product.video:
                    delete_local_file(product.video)

                # حذف الريلز المرتبطة بالمنتج
                models.Reel.query.filter_by(product_id=product.id).delete()

                # حذف العلاقات المرتبطة بالمنتج
                models.ProductReaction.query.filter_by(product_id=product.id).delete()
                models.ProductComment.query.filter_by(product_id=product.id).delete()
                models.Favorite.query.filter_by(product_id=product.id).delete()
                models.Review.query.filter_by(product_id=product.id).delete()
                db.session.delete(product)

            # حذف الريلز المتبقية المرتبطة بالمتجر
            models.Reel.query.filter_by(store_id=store.id).delete()

            # حذف التصنيفات والاشتراكات والمدفوعات والمفضلات
            Category.query.filter_by(store_id=store.id).delete()
            Subscription.query.filter_by(store_id=store.id).delete()
            Payment.query.filter_by(store_id=store.id).delete()
            Favorite.query.filter_by(store_id=store.id).delete()

            StoreRepository.delete(store)
            db.session.commit()
            return True, 'تم حذف المتجر بنجاح'
        except Exception as e:
            db.session.rollback()
            logger.error(f'خطأ في حذف المتجر {store_id}: {str(e)}')
            return False, 'حدث خطأ أثناء حذف المتجر'
