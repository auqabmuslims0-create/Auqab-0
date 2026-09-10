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
    def _activate_subscription(sub, override_days=None, override_end_date=None,
                               override_amount=None, admin_note=None):
        try:
            sub.status = 'paid'
            sub.start_date = current_time()

            if override_end_date is not None:
                sub.end_date = override_end_date
                try:
                    delta = override_end_date - sub.start_date
                    sub.duration_days = max(1, int(delta.days))
                except Exception:
                    pass
            elif override_days is not None:
                sub.duration_days = int(override_days)
                sub.end_date = sub.start_date + timedelta(days=int(override_days))
            else:
                sub.end_date = sub.start_date + timedelta(days=sub.duration_days or 30)

            if override_amount is not None:
                sub.amount = float(override_amount)

            if admin_note:
                sub.admin_note = (sub.admin_note + '\n' if sub.admin_note else '') + admin_note

            sub.confirmation_attempts = 0
            sub.confirmation_expiry = None
            sub.expiry_notified = False
            db.session.add(sub)

            store = None
            if sub.store_id:
                store = db.session.get(Store, sub.store_id)
                if store:
                    store.subscription_status = 'active'
                    store.subscription_expiry = sub.end_date
                    db.session.add(store)

            payments = PaymentRepository.get_by_subscription(sub.id)
            for p in payments:
                if p.status == 'pending':
                    if override_amount is not None:
                        p.amount = float(override_amount)
                    p.status = 'paid'
                    db.session.add(p)

            notify_user_id = None
            notify_store_name = 'متجرك'
            if store and store.owner_id:
                notify_user_id = store.owner_id
                notify_store_name = f'"{store.name}"'
            elif sub.user_id:
                notify_user_id = sub.user_id

            if notify_user_id:
                try:
                    NotificationService.send_to_user(
                        user_id=notify_user_id,
                        title='تم تفعيل الاشتراك',
                        message=f'تم تفعيل اشتراك متجرك {notify_store_name} بنجاح حتى {sub.end_date.strftime("%Y-%m-%d")}.',
                        link=url_for('store.store_subscription', store_id=sub.store_id) if sub.store_id else url_for('auth.dashboard'),
                        type_=NotificationService.TYPE_SUBSCRIPTION,
                        priority=NotificationService.PRIORITY_IMPORTANT,
                        commit=False
                    )
                except Exception as ne:
                    logger.warning(f'تعذر إرسال إشعار التفعيل للاشتراك {sub.id}: {ne}')

            db.session.commit()
            return True, 'تم تفعيل الاشتراك بنجاح'
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في تفعيل الاشتراك {sub.id}: {str(e)}")
            return False, 'حدث خطأ أثناء تفعيل الاشتراك'

    @staticmethod
    def approve_subscription(sub_id, override_days=None, override_end_date=None,
                             override_amount=None, admin_note=None):
        sub = SubscriptionRepository.get_by_id(sub_id)
        if not sub:
            return False, 'الاشتراك غير موجود'
        if sub.status != 'pending':
            return False, 'الاشتراك ليس قيد الانتظار'
        return SubscriptionService._activate_subscription(
            sub,
            override_days=override_days,
            override_end_date=override_end_date,
            override_amount=override_amount,
            admin_note=admin_note
        )

    @staticmethod
    def reject_subscription(sub_id, admin_note=None):
        sub = SubscriptionRepository.get_by_id(sub_id)
        if not sub:
            return False, 'الاشتراك غير موجود'
        try:
            sub.status = 'cancelled'
            if admin_note:
                sub.admin_note = (sub.admin_note + '\n' if sub.admin_note else '') + admin_note
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
                        link=url_for('store.store_subscription', store_id=sub.store_id) if sub.store_id else url_for('auth.dashboard'),
                        type_=NotificationService.TYPE_SUBSCRIPTION,
                        priority=NotificationService.PRIORITY_URGENT,
                        commit=False
                    )

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
    def extend_subscription(sub_id, days, admin_note=None):
        if days is None or int(days) <= 0:
            return False, 'عدد الأيام غير صالح'
        sub = SubscriptionRepository.get_by_id(sub_id)
        if not sub:
            return False, 'الاشتراك غير موجود'
        try:
            days = int(days)
            base = sub.end_date if sub.end_date and sub.end_date > current_time() else current_time()
            sub.end_date = base + timedelta(days=days)
            sub.duration_days = (sub.duration_days or 0) + days
            sub.renewal_count = (sub.renewal_count or 0) + 1
            if admin_note:
                sub.admin_note = (sub.admin_note + '\n' if sub.admin_note else '') + admin_note
            db.session.add(sub)

            store = None
            if sub.store_id:
                store = db.session.get(Store, sub.store_id)
                if store:
                    store.subscription_status = 'active'
                    store.subscription_expiry = sub.end_date
                    db.session.add(store)

            if sub.status in ['expired', 'suspended', 'cancelled']:
                sub.status = 'paid'

            db.session.commit()

            if store and store.owner_id:
                try:
                    NotificationService.send_to_user(
                        user_id=store.owner_id,
                        title='تم تمديد الاشتراك',
                        message=f'تم تمديد اشتراك متجرك "{store.name}" حتى {sub.end_date.strftime("%Y-%m-%d")}.',
                        link=url_for('store.store_subscription', store_id=store.id),
                        type_=NotificationService.TYPE_SUBSCRIPTION,
                        priority=NotificationService.PRIORITY_IMPORTANT
                    )
                    db.session.commit()
                except Exception as ne:
                    logger.warning(f'تعذر إرسال إشعار التمديد: {ne}')

            return True, f'تم تمديد الاشتراك {days} يوم'
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في تمديد الاشتراك {sub.id}: {str(e)}")
            return False, 'حدث خطأ أثناء التمديد'

    @staticmethod
    def set_subscription_end_date(sub_id, new_end_date, admin_note=None):
        sub = SubscriptionRepository.get_by_id(sub_id)
        if not sub:
            return False, 'الاشتراك غير موجود'
        if not new_end_date:
            return False, 'تاريخ الانتهاء مطلوب'
        try:
            sub.end_date = new_end_date
            if sub.start_date:
                delta = new_end_date - sub.start_date
                sub.duration_days = max(1, int(delta.days))
            if admin_note:
                sub.admin_note = (sub.admin_note + '\n' if sub.admin_note else '') + admin_note
            db.session.add(sub)

            if sub.store_id:
                store = db.session.get(Store, sub.store_id)
                if store:
                    if new_end_date > current_time():
                        store.subscription_status = 'active'
                        store.subscription_expiry = new_end_date
                        if sub.status in ['expired', 'cancelled', 'suspended']:
                            sub.status = 'paid'
                    else:
                        store.subscription_status = 'expired'
                        store.subscription_expiry = new_end_date
                    db.session.add(store)

            db.session.commit()
            return True, 'تم تحديث تاريخ الانتهاء'
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في تعديل تاريخ الانتهاء للاشتراك {sub.id}: {str(e)}")
            return False, 'حدث خطأ أثناء التعديل'

    @staticmethod
    def extend_store_subscription(store_id, days, admin_note=None):
        if days is None or int(days) <= 0:
            return False, 'عدد الأيام غير صالح'
        store = db.session.get(Store, store_id)
        if not store:
            return False, 'المتجر غير موجود'
        active_sub = SubscriptionRepository.get_active_subscription_for_store(store_id)
        if active_sub:
            return SubscriptionService.extend_subscription(active_sub.id, days=days, admin_note=admin_note)
        try:
            from shared.services.store_service import StoreService
            new_sub = StoreService._create_admin_subscription(store, days=int(days))
            if admin_note:
                new_sub.admin_note = admin_note
            store.subscription_status = 'active'
            store.subscription_expiry = new_sub.end_date
            db.session.add(store)
            db.session.add(new_sub)
            db.session.commit()
            return True, f'تم إنشاء اشتراك إداري لـ {days} يوم'
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في إنشاء اشتراك إداري للمتجر {store_id}: {str(e)}")
            return False, 'حدث خطأ'

    @staticmethod
    def update_store_subscription_settings(store_id, custom_price=None, custom_duration_days=None,
                                           grace_days=None, notes=None, auto_renew=None):
        store = db.session.get(Store, store_id)
        if not store:
            return False, 'المتجر غير موجود'
        try:
            if custom_price is not None and custom_price < 0:
                return False, 'السعر المخصص لا يمكن أن يكون سالبًا'
            if custom_duration_days is not None and custom_duration_days <= 0:
                return False, 'المدة المخصصة يجب أن تكون أكبر من صفر'
            if grace_days is not None and grace_days < 0:
                return False, 'أيام السماح لا يمكن أن تكون سالبة'

            store.custom_subscription_price = custom_price
            store.custom_subscription_duration_days = custom_duration_days
            store.subscription_grace_days = grace_days
            store.subscription_notes = notes
            if auto_renew is not None:
                store.auto_renew = bool(auto_renew)
            db.session.add(store)
            db.session.commit()

            if store.owner_id:
                try:
                    NotificationService.send_to_user(
                        user_id=store.owner_id,
                        title='تحديث إعدادات الاشتراك',
                        message=f'قام المدير بتحديث إعدادات اشتراك متجرك "{store.name}".',
                        link=url_for('store.store_subscription', store_id=store.id),
                        type_=NotificationService.TYPE_SUBSCRIPTION,
                        priority=NotificationService.PRIORITY_IMPORTANT
                    )
                    db.session.commit()
                except Exception as ne:
                    logger.warning(f'تعذر إرسال إشعار تحديث الإعدادات: {ne}')

            return True, 'تم تحديث إعدادات الاشتراك'
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في تحديث إعدادات اشتراك المتجر {store_id}: {str(e)}")
            return False, 'حدث خطأ أثناء الحفظ'

    @staticmethod
    def suspend_store_subscription(store_id, reason=None):
        store = db.session.get(Store, store_id)
        if not store:
            return False, 'المتجر غير موجود'
        try:
            store.subscription_status = 'suspended'
            db.session.add(store)

            active_sub = SubscriptionRepository.get_active_subscription_for_store(store_id)
            if active_sub:
                active_sub.status = 'suspended'
                if reason:
                    active_sub.admin_note = (active_sub.admin_note + '\n' if active_sub.admin_note else '') + reason
                db.session.add(active_sub)

            db.session.commit()

            if store.owner_id:
                try:
                    NotificationService.send_to_user(
                        user_id=store.owner_id,
                        title='تم إيقاف اشتراك المتجر',
                        message=f'تم إيقاف اشتراك متجرك "{store.name}" من قبل الإدارة.',
                        link=url_for('store.store_subscription', store_id=store.id),
                        type_=NotificationService.TYPE_ALERT,
                        priority=NotificationService.PRIORITY_URGENT
                    )
                    db.session.commit()
                except Exception as ne:
                    logger.warning(f'تعذر إرسال إشعار الإيقاف: {ne}')

            return True, 'تم إيقاف اشتراك المتجر'
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في إيقاف اشتراك المتجر {store_id}: {str(e)}")
            return False, 'حدث خطأ أثناء الإيقاف'

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
                        priority=NotificationService.PRIORITY_URGENT,
                        commit=False
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
                store = None
                if sub.store_id:
                    store = db.session.get(Store, sub.store_id)

                # 1) احترام أيام السماح الخاصة بالمتجر
                grace_days = 0
                if store and store.subscription_grace_days:
                    try:
                        grace_days = int(store.subscription_grace_days)
                    except (TypeError, ValueError):
                        grace_days = 0

                if grace_days > 0 and sub.end_date:
                    effective_end = sub.end_date + timedelta(days=grace_days)
                    if effective_end > now:
                        if store:
                            store.subscription_status = 'active'
                            store.subscription_expiry = effective_end
                            db.session.add(store)
                        continue

                # 2) التجديد التلقائي: إنشاء اشتراك معلّق بدل الإنهاء
                if store and store.auto_renew:
                    existing_pending = SubscriptionRepository.get_pending_subscription_for_store(store.id)
                    if not existing_pending:
                        # المدة
                        if store.custom_subscription_duration_days is not None:
                            try:
                                duration = int(store.custom_subscription_duration_days)
                            except (TypeError, ValueError):
                                duration = int(get_setting('subscription_duration_days', 30))
                        else:
                            duration = int(get_setting('subscription_duration_days', 30))

                        # السعر
                        if store.custom_subscription_price is not None:
                            try:
                                price = float(store.custom_subscription_price)
                            except (TypeError, ValueError):
                                price = float(get_setting('subscription_price', 500))
                        else:
                            price = float(get_setting('subscription_price', 500))

                        new_sub = Subscription(
                            user_id=store.owner_id,
                            store_id=store.id,
                            start_date=current_time(),
                            end_date=current_time() + timedelta(days=duration),
                            amount=price,
                            status='pending',
                            payment_method='manual_delivery',
                            duration_days=duration,
                            renewal_count=(sub.renewal_count or 0) + 1,
                            admin_note='تم إنشاء طلب تجديد تلقائي عند انتهاء الاشتراك.'
                        )
                        db.session.add(new_sub)

                        sub.status = 'expired'
                        store.subscription_status = 'pending'
                        store.subscription_expiry = sub.end_date
                        db.session.add(sub)
                        db.session.add(store)

                        if store.owner_id:
                            owner = db.session.get(User, store.owner_id)
                            if owner:
                                NotificationService.send_to_user(
                                    user_id=owner.id,
                                    title='تجديد تلقائي للاشتراك',
                                    message=f'انتهى اشتراك متجرك "{store.name}" وتم إنشاء طلب تجديد تلقائي بمبلغ {price} ل.س. يرجى إتمام الدفع.',
                                    link=url_for('store.subscription_pending', store_id=store.id),
                                    type_=NotificationService.TYPE_SUBSCRIPTION,
                                    priority=NotificationService.PRIORITY_URGENT,
                                    commit=False
                                )
                        count += 1
                        continue

                # 3) الإنهاء العادي
                sub.status = 'expired'
                db.session.add(sub)

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
                            message=f'انتهى اشتراك متجرك "{sub.store.name if sub.store else ""}". يرجى التجديد لاستئناف الخدمة.',
                            link=url_for('store.store_subscription', store_id=sub.store_id) if sub.store_id else url_for('auth.dashboard'),
                            type_=NotificationService.TYPE_SUBSCRIPTION,
                            priority=NotificationService.PRIORITY_URGENT,
                            commit=False
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
            if store.custom_subscription_price is not None:
                subscription_price = float(store.custom_subscription_price)
            else:
                subscription_price = float(get_setting('subscription_price', 500))
        except (TypeError, ValueError):
            subscription_price = 500.0

        try:
            if store.custom_subscription_duration_days is not None:
                duration_days = int(store.custom_subscription_duration_days)
            else:
                duration_days = int(get_setting('subscription_duration_days', 30))
        except (TypeError, ValueError):
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
        if sub.user_id is None or sub.user_id != user.id:
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
