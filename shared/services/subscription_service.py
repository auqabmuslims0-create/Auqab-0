import logging
import os
import secrets
from datetime import timedelta

from database import db
from models import User, Store, Subscription, Payment
from shared.repositories.subscription_repository import SubscriptionRepository
from shared.repositories.payment_repository import PaymentRepository
from shared.repositories.notification_repository import NotificationRepository
from shared.services.payment_service import PaymentService
from shared.services.notification_service import NotificationService
from shared.utils import save_image, get_upload_path, get_setting
from shared.time_utils import current_time
from flask import url_for

logger = logging.getLogger(__name__)


class SubscriptionService:
    @staticmethod
    def _activate_subscription(sub):
        try:
            sub.status = 'paid'
            sub.start_date = current_time()
            sub.end_date = current_time() + timedelta(days=sub.duration_days or 30)
            sub.confirmation_attempts = 0
            sub.confirmation_expiry = None
            db.session.add(sub)

            if sub.store_id:
                store = db.session.get(Store, sub.store_id)
                if store:
                    store.subscription_status = 'active'
                    store.subscription_expiry = sub.end_date
                    db.session.add(store)

            # تحديث المدفوعات المرتبطة إلى paid
            payments = PaymentRepository.get_by_subscription(sub.id)
            for p in payments:
                if p.status == 'pending':
                    p.status = 'paid'
                    db.session.add(p)

            # إرسال إشعار لصاحب المتجر
            if sub.user_id:
                user = db.session.get(User, sub.user_id)
                if user:
                    NotificationService.send_to_user(
                        user_id=user.id,
                        title='تم تفعيل الاشتراك',
                        message=f'تم تفعيل اشتراك متجرك "{sub.store.name}" بنجاح حتى {sub.end_date.strftime("%Y-%m-%d")}.',
                        link=url_for('store.store_subscription', store_id=sub.store_id) if sub.store_id else url_for('dashboard'),
                        type_=NotificationService.TYPE_SUBSCRIPTION,
                        priority=NotificationService.PRIORITY_IMPORTANT
                    )

            db.session.commit()
            return True, 'تم تفعيل الاشتراك بنجاح'
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في تفعيل الاشتراك {sub.id}: {str(e)}")
            return False, 'حدث خطأ أثناء تفعيل الاشتراك'

    @staticmethod
    def approve_subscription(sub_id):
        sub = SubscriptionRepository.get_by_id(sub_id)
        if not sub:
            return False, 'الاشتراك غير موجود'
        if sub.status != 'pending':
            return False, 'الاشتراك ليس قيد الانتظار'
        return SubscriptionService._activate_subscription(sub)

    @staticmethod
    def reject_subscription(sub_id):
        sub = SubscriptionRepository.get_by_id(sub_id)
        if not sub:
            return False, 'الاشتراك غير موجود'
        try:
            sub.status = 'cancelled'
            db.session.add(sub)

            if sub.store_id:
                store = db.session.get(Store, sub.store_id)
                if store:
                    store.subscription_status = 'cancelled'
                    store.subscription_expiry = None
                    db.session.add(store)

            if sub.user_id:
                user = db.session.get(User, sub.user_id)
                if user:
                    NotificationService.send_to_user(
                        user_id=user.id,
                        title='تم رفض الاشتراك',
                        message='تم رفض طلب اشتراك متجرك. يرجى التواصل مع الإدارة لمزيد من التفاصيل.',
                        link=url_for('store.store_subscription', store_id=sub.store_id) if sub.store_id else url_for('dashboard'),
                        type_=NotificationService.TYPE_SUBSCRIPTION,
                        priority=NotificationService.PRIORITY_URGENT
                    )

            # تحديث المدفوعات المعلقة إلى failed
            payments = PaymentRepository.get_by_subscription(sub.id)
            for p in payments:
                if p.status == 'pending':
                    p.status = 'failed'
                    db.session.add(p)

            db.session.commit()
            return True, 'تم رفض الاشتراك'
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في رفض الاشتراك {sub.id}: {str(e)}")
            return False, 'حدث خطأ أثناء رفض الاشتراك'

    @staticmethod
    def check_expiring_subscriptions(days=3):
        threshold = current_time() + timedelta(days=days)
        expiring_subs = SubscriptionRepository.get_expiring_subscriptions(threshold)
        for sub in expiring_subs:
            if sub.store and sub.store.owner_id:
                owner = db.session.get(User, sub.store.owner_id)
                if owner:
                    NotificationService.send_to_user(
                        user_id=owner.id,
                        title='تنبيه انتهاء الاشتراك',
                        message=f'سينتهي اشتراك متجرك "{sub.store.name}" بتاريخ {sub.end_date.strftime("%Y-%m-%d")}. يرجى التجديد لتجنب انقطاع الخدمة.',
                        link=url_for('store.store_subscription', store_id=sub.store.id),
                        type_=NotificationService.TYPE_SUBSCRIPTION,
                        priority=NotificationService.PRIORITY_URGENT
                    )
            sub.expiry_notified = True
            db.session.add(sub)
        if expiring_subs:
            db.session.commit()
        return len(expiring_subs)

    @staticmethod
    def expire_subscriptions():
        now = current_time()
        expired_subs = SubscriptionRepository.get_expired_subscriptions(now)

        count = 0
        for sub in expired_subs:
            try:
                sub.status = 'expired'
                db.session.add(sub)

                if sub.store_id:
                    store = db.session.get(Store, sub.store_id)
                    if store:
                        store.subscription_status = 'expired'
                        store.subscription_expiry = sub.end_date
                        db.session.add(store)

                if sub.user_id:
                    user = db.session.get(User, sub.user_id)
                    if user:
                        NotificationService.send_to_user(
                            user_id=user.id,
                            title='انتهاء الاشتراك',
                            message=f'انتهى اشتراك متجرك "{sub.store.name}". يرجى التجديد لاستئناف الخدمة.',
                            link=url_for('store.store_subscription', store_id=sub.store_id) if sub.store_id else url_for('dashboard'),
                            type_=NotificationService.TYPE_SUBSCRIPTION,
                            priority=NotificationService.PRIORITY_URGENT
                        )
                count += 1
            except Exception as e:
                logger.error(f"خطأ في معالجة الاشتراك المنتهي {sub.id}: {str(e)}")
                db.session.rollback()
        if count > 0:
            try:
                db.session.commit()
            except Exception as e:
                logger.error(f"فشل حفظ تغييرات الاشتراكات المنتهية: {str(e)}")
                db.session.rollback()
        return count

    @staticmethod
    def submit_subscription_request(user, store, payment_ref=None, proof_file=None, payment_method='wallet'):
        try:
            subscription_price = float(get_setting('subscription_price', 500))
            duration_days = int(get_setting('subscription_duration_days', 30))
        except (TypeError, ValueError):
            subscription_price = 500.0
            duration_days = 30

        if store.owner_id != user.id:
            return False, 'غير مسموح لك بتقديم طلب اشتراك لهذا المتجر', None

        active_sub = SubscriptionRepository.get_active_subscription_for_store(store.id)
        if active_sub:
            return False, 'لديك اشتراك نشط بالفعل. يمكنك التجديد عند انتهائه.', None

        pending_sub = SubscriptionRepository.get_pending_subscription_for_store(store.id)

        sub = pending_sub
        if not sub:
            sub = SubscriptionRepository.create({
                'user_id': user.id,
                'store_id': store.id,
                'start_date': current_time(),
                'end_date': current_time() + timedelta(days=duration_days),
                'amount': subscription_price,
                'status': 'pending',
                'payment_method': payment_method,
                'duration_days': duration_days,
                'renewal_count': 0
            })
            db.session.add(sub)
        else:
            sub.amount = subscription_price
            sub.start_date = current_time()
            sub.payment_method = payment_method
            sub.duration_days = duration_days
            db.session.add(sub)

        sub.status = 'pending'

        try:
            if payment_method == 'manual_delivery':
                if not sub.confirmation_code:
                    sub.confirmation_code = ''.join(secrets.choice('0123456789') for _ in range(6))
                if sub.proof_image:
                    old_proof = get_upload_path(sub.proof_image)
                    if old_proof and os.path.exists(old_proof):
                        try:
                            os.remove(old_proof)
                        except Exception:
                            pass
                    sub.proof_image = None
                sub.payment_ref = None
                sub.confirmation_attempts = 0
                sub.confirmation_expiry = current_time() + timedelta(hours=24)

                existing_payment = Payment.query.filter_by(
                    subscription_id=sub.id,
                    status='pending',
                    method='manual_delivery'
                ).first()

                if existing_payment:
                    existing_payment.amount = subscription_price
                    existing_payment.reference = sub.confirmation_code
                    existing_payment.proof_image = None
                    existing_payment.notes = 'تسليم يدوي'
                    db.session.add(existing_payment)
                else:
                    payment, err = PaymentService.create_payment(
                        user_id=user.id,
                        amount=subscription_price,
                        method='manual_delivery',
                        subscription_id=sub.id,
                        store_id=store.id,
                        reference=sub.confirmation_code,
                        proof_image=None,
                        notes='تسليم يدوي'
                    )
                    if not payment:
                        raise ValueError(f'تعذر تسجيل الدفع: {err}')

            else:
                if not payment_ref:
                    raise ValueError('يجب إدخال رقم العملية')
                sub.payment_ref = payment_ref

                if proof_file and proof_file.filename != '':
                    new_proof = save_image(proof_file)
                    if new_proof:
                        if sub.proof_image:
                            old_proof = get_upload_path(sub.proof_image)
                            if old_proof and os.path.exists(old_proof):
                                try:
                                    os.remove(old_proof)
                                except Exception:
                                    pass
                        sub.proof_image = new_proof

                existing_payment = Payment.query.filter_by(
                    subscription_id=sub.id,
                    status='pending'
                ).first()

                if existing_payment:
                    existing_payment.amount = subscription_price
                    existing_payment.method = payment_method
                    existing_payment.reference = payment_ref
                    existing_payment.proof_image = sub.proof_image
                    existing_payment.notes = 'اشتراك متجر'
                    db.session.add(existing_payment)
                else:
                    payment, err = PaymentService.create_payment(
                        user_id=user.id,
                        amount=subscription_price,
                        method=payment_method,
                        subscription_id=sub.id,
                        store_id=store.id,
                        reference=payment_ref,
                        proof_image=sub.proof_image,
                        notes='اشتراك متجر'
                    )
                    if not payment:
                        raise ValueError(f'تعذر تسجيل الدفع: {err}')

            db.session.commit()
            return True, 'تم إرسال طلب الاشتراك بنجاح', sub
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في تقديم طلب الاشتراك للمتجر {store.id}: {str(e)}")
            return False, str(e), None

    @staticmethod
    def verify_manual_confirmation(user, sub_id, code):
        sub = SubscriptionRepository.get_by_id(sub_id)
        if not sub:
            return False, 'الاشتراك غير موجود'
        if sub.user_id != user.id:
            return False, 'غير مسموح'
        if sub.payment_method != 'manual_delivery':
            return False, 'طريقة الدفع غير صحيحة'
        if sub.status != 'pending':
            return False, 'الاشتراك ليس قيد الانتظار'
        if not sub.confirmation_code:
            return False, 'لا يوجد كود تأكيد'
        if sub.confirmation_attempts >= 5:
            return False, 'تم تجاوز الحد الأقصى لمحاولات التأكيد. يرجى التواصل مع الإدارة.'
        if sub.confirmation_expiry and sub.confirmation_expiry < current_time():
            return False, 'انتهت صلاحية كود التأكيد. يرجى إعادة الطلب.'
        if sub.confirmation_code != code.strip():
            sub.confirmation_attempts += 1
            db.session.add(sub)
            db.session.commit()
            remaining = 5 - sub.confirmation_attempts
            if remaining <= 0:
                return False, 'تم تجاوز الحد الأقصى للمحاولات. يرجى التواصل مع الإدارة.'
            return False, f'كود التأكيد غير صحيح. تبقى {remaining} محاولات.'

        return SubscriptionService._activate_subscription(sub)
