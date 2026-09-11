from database import db
from flask import url_for
from models import User, Order, OrderItem, Product, Payment, OrderStatusHistory
from shared.repositories.order_repository import OrderRepository
from shared.repositories.product_repository import ProductRepository
from shared.repositories.store_repository import StoreRepository
from shared.repositories.user_repository import UserRepository
from shared.services.notification_service import NotificationService
from shared.services.payment_service import PaymentService
from shared.utils import get_setting, is_store_active, is_store_open
from shared.delivery_utils import is_delivery_available
from shared.time_utils import current_time
import random
import logging

logger = logging.getLogger(__name__)


class OrderService:
    # مصفوفة الانتقالات المسموحة بين حالات الطلب
    ALLOWED_TRANSITIONS = {
        'new': ['confirmed', 'cancelled'],
        'confirmed': ['preparing', 'cancelled'],
        'preparing': ['ready', 'cancelled'],
        'ready': ['delivering', 'cancelled'],
        'delivering': ['delivered', 'cancelled'],
        'delivered': [],
        'cancelled': []
    }

    # E8: نصوص عربية موحّدة لكل حالة (تُستخدم في الإشعارات والواجهات)
    STATUS_LABELS = {
        'new': 'جديد',
        'confirmed': 'تم التأكيد',
        'preparing': 'قيد التجهيز',
        'ready': 'جاهز للتسليم',
        'delivering': 'في الطريق إليك',
        'delivered': 'تم التسليم بنجاح',
        'cancelled': 'ملغي',
    }

    @staticmethod
    def generate_delivery_code():
        return ''.join(random.choices('0123456789', k=6))

    @staticmethod
    def generate_pickup_code():
        """S13: كود استلام من المتجر (6 أرقام)."""
        return ''.join(random.choices('0123456789', k=6))

    @staticmethod
    def status_label(status):
        """E8: النص العربي لحالة الطلب."""
        return OrderService.STATUS_LABELS.get(status, status)

    @staticmethod
    def get_effective_price(product):
        return product.offer_price if product.is_offer and product.offer_price is not None else product.price

    @staticmethod
    def _check_store_active(store):
        if not is_store_active(store):
            raise ValueError('هذا المتجر غير نشط حالياً ولا يمكن الطلب منه')

    @staticmethod
    def _check_store_open(store):
        if store.working_hours and not is_store_open(store):
            raise ValueError('المتجر مغلق حالياً ولا يمكن الطلب منه')

    @staticmethod
    def create_order(user, store, cart_items=None, items_data=None, delivery_address=None,
                     latitude=None, longitude=None, payment_method='cash', customer_note=None):
        if not user or not store:
            raise ValueError("بيانات الطلب غير مكتملة")

        OrderService._check_store_active(store)
        OrderService._check_store_open(store)

        order_items = []
        if cart_items is not None:
            for item in cart_items:
                if 'product' not in item or 'quantity' not in item:
                    raise ValueError('بيانات السلة غير صحيحة')
                product = item['product']
                qty = item['quantity']
                options_selected = item.get('options_selected')
                if not product or product.store_id != store.id:
                    raise ValueError(f"المنتج {product.name if product else 'غير معروف'} لا يخص هذا المتجر")
                order_items.append((product, qty, options_selected))
        elif items_data is not None:
            for item in items_data:
                product_id = item.get('product_id')
                qty = item.get('quantity', 1)
                options_selected = item.get('options_selected')
                if not product_id or qty <= 0:
                    raise ValueError('بيانات المنتج غير صحيحة')
                product = ProductRepository.get_by_id(product_id)
                if not product:
                    raise ValueError(f'المنتج رقم {product_id} غير موجود')
                if product.store_id != store.id:
                    raise ValueError('يجب أن تكون جميع المنتجات من نفس المتجر')
                order_items.append((product, qty, options_selected))
        else:
            raise ValueError("يجب توفير cart_items أو items_data")

        if not order_items:
            raise ValueError('لا توجد منتجات صالحة في الطلب')

        for product, qty, _ in order_items:
            if product.stock_quantity < qty:
                raise ValueError(f"المخزون غير كافٍ للمنتج {product.name}")

        # S6: منع طلب المنتجات المخفية السعر أونلاين (حصراً من المتجر)
        hidden_price_products = [p for p, _, _ in order_items if p.hide_price]
        if hidden_price_products:
            names = '، '.join(p.name for p in hidden_price_products[:3])
            raise ValueError(
                f'المنتجات التالية حصراً من المتجر ولا يمكن طلبها أونلاين: {names}'
            )

        product_total = sum(OrderService.get_effective_price(product) * qty for product, qty, _ in order_items)
        delivery_fee = float(get_setting('delivery_fee', 100)) if store.has_delivery else 0.0
        grand_total = product_total + delivery_fee

        if store.has_delivery:
            if not delivery_address:
                raise ValueError("العنوان مطلوب لخدمة التوصيل")
            if latitude is None or longitude is None:
                raise ValueError("يجب تحديد موقع التوصيل على الخريطة")

        order = OrderRepository.create_order({
            'customer_id': user.id,
            'store_id': store.id,
            'status': 'new',
            'total': grand_total,
            'delivery_fee': delivery_fee,
            'delivery_code': OrderService.generate_delivery_code(),
            'delivery_address': delivery_address if store.has_delivery else None,
            'latitude': latitude if store.has_delivery else None,
            'longitude': longitude if store.has_delivery else None,
            'is_cancelled': False,
            'payment_method': payment_method,
            'customer_note': customer_note or None
        })
        db.session.flush()

        PaymentService.create_payment(
            user_id=user.id,
            amount=grand_total,
            method=payment_method,
            order_id=order.id,
            store_id=store.id,
            reference=None,
            proof_image=None,
            notes='طلب جديد'
        )

        for product, qty, options_selected in order_items:
            product.stock_quantity -= qty
            db.session.add(product)
            OrderRepository.add_item(
                order_id=order.id,
                product_id=product.id,
                quantity=qty,
                price=OrderService.get_effective_price(product),
                options_selected=options_selected
            )

        OrderRepository.add_status_history(
            order_id=order.id,
            from_status=None,
            to_status='new',
            changed_by=user.id,
            note='إنشاء الطلب'
        )

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise ValueError('حدث خطأ أثناء إنشاء الطلب، حاول مرة أخرى')

        try:
            NotificationService.send_to_store_owner(
                store,
                f"طلب جديد رقم {order.id} من {user.username}",
                title="طلب جديد",
                link=f"/store/{store.id}/orders"
            )
        except Exception as e:
            logger.error(f'فشل إرسال إشعار إلى صاحب المتجر: {str(e)}')

        return order

    @staticmethod
    def cancel_order(user, order):
        if order.customer_id != user.id:
            raise PermissionError("لا يمكنك إلغاء هذا الطلب")
        if order.status not in ['new', 'confirmed', 'preparing']:
            raise ValueError("لا يمكن إلغاء هذا الطلب في حالته الحالية")

        for item in order.items:
            product = item.product
            if product:
                product.stock_quantity += item.quantity
                db.session.add(product)

        from_status = order.status
        order.status = 'cancelled'
        order.is_cancelled = True
        order.updated_at = current_time()
        OrderRepository.update_order(order)

        OrderRepository.add_status_history(
            order_id=order.id,
            from_status=from_status,
            to_status='cancelled',
            changed_by=user.id,
            note='إلغاء من قبل الزبون'
        )

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise ValueError('حدث خطأ أثناء إلغاء الطلب')

        if order.store:
            try:
                NotificationService.send_to_store_owner(
                    order.store,
                    f"قام الزبون {user.username} بإلغاء الطلب رقم {order.id}",
                    title="إلغاء طلب",
                    link=f"/store/{order.store.id}/orders"
                )
            except Exception as e:
                logger.error(f'فشل إرسال إشعار إلغاء الطلب: {str(e)}')

        return order

    @staticmethod
    def start_delivery(delivery_user, order, pickup_code=None):
        """S13: بدء التسليم يتطلب التحقق من كود الاستلام من المتجر."""
        if order.delivery_person_id != delivery_user.id:
            raise PermissionError("هذا الطلب غير مخصص لك")
        if order.status != 'ready':
            raise ValueError("لا يمكن بدء التسليم الآن")
        if not order.pickup_code:
            raise ValueError("رمز الاستلام من المتجر غير موجود لهذا الطلب")
        if not pickup_code:
            raise ValueError("يرجى إدخال رمز الاستلام من المتجر")
        if pickup_code.strip() != order.pickup_code:
            raise ValueError("رمز الاستلام غير صحيح")

        from_status = order.status
        order.status = 'delivering'
        order.updated_at = current_time()
        OrderRepository.update_order(order)

        OrderRepository.add_status_history(
            order_id=order.id,
            from_status=from_status,
            to_status='delivering',
            changed_by=delivery_user.id,
            note='استلم المندوب الطلب من المتجر'
        )

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise ValueError('حدث خطأ أثناء بدء التسليم')

        if order.store:
            try:
                NotificationService.send_to_store_owner(
                    order.store,
                    f"المندوب {delivery_user.username} استلم الطلب رقم {order.id} وهو في الطريق",
                    title="الطلب في الطريق",
                    link=f"/store/{order.store.id}/orders"
                )
            except Exception as e:
                logger.error(f'فشل إرسال إشعار بدء التسليم: {str(e)}')

        if order.customer_id:
            try:
                NotificationService.send_to_user(
                    user_id=order.customer_id,
                    message=f"طلبك رقم {order.id} من متجر {order.store.name if order.store else ''} في الطريق إليك",
                    title="طلبك في الطريق",
                    link=url_for('cart.cart'),
                    type_=NotificationService.TYPE_ORDER
                )
            except Exception as e:
                logger.error(f'فشل إرسال إشعار للزبون: {str(e)}')

        return order

    @staticmethod
    def complete_delivery(delivery_user, order, delivery_code):
        if order.delivery_person_id != delivery_user.id:
            raise PermissionError("هذا الطلب غير مخصص لك")
        if order.status != 'delivering':
            raise ValueError("لا يمكن التسليم الآن")
        if not order.delivery_code:
            raise ValueError("رمز التسليم غير موجود لهذا الطلب")
        if not delivery_code:
            raise ValueError("رمز التسليم مطلوب")
        if delivery_code != order.delivery_code:
            raise ValueError("رمز التسليم غير صحيح")

        from_status = order.status
        order.status = 'delivered'
        order.delivered_at = current_time()
        order.updated_at = current_time()
        OrderRepository.update_order(order)

        OrderRepository.add_status_history(
            order_id=order.id,
            from_status=from_status,
            to_status='delivered',
            changed_by=delivery_user.id,
            note='تسليم ناجح'
        )

        payments = Payment.query.filter_by(order_id=order.id).all()
        for p in payments:
            if p.status == 'pending' and p.method == 'cash':
                p.status = 'paid'

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise ValueError('حدث خطأ أثناء تأكيد التسليم')

        if order.store:
            try:
                NotificationService.send_to_store_owner(
                    order.store,
                    f"تم تسليم الطلب رقم {order.id} بنجاح",
                    title="طلب مُسلَّم",
                    link=f"/store/{order.store.id}/orders"
                )
            except Exception as e:
                logger.error(f'فشل إرسال إشعار تسليم لصاحب المتجر: {str(e)}')

        if order.customer_id:
            try:
                NotificationService.send_to_user(
                    order.customer_id,
                    f"تم تسليم طلبك رقم {order.id} بنجاح",
                    title="تم التسليم",
                    link=url_for('cart.cart'),
                    type_=NotificationService.TYPE_ORDER
                )
            except Exception as e:
                logger.error(f'فشل إرسال إشعار تسليم للزبون: {str(e)}')

        return order

    @staticmethod
    def _apply_status_update(order, new_status, actor_id, note='',
                             delivery_person_id=None, notify_delivery=False):
        if order.status == 'cancelled':
            raise ValueError('هذا الطلب ملغي ولا يمكن تغيير حالته')

        if new_status not in ['confirmed', 'preparing', 'ready', 'delivering', 'delivered', 'cancelled']:
            raise ValueError('حالة غير صالحة')

        current_status = order.status
        allowed_next = OrderService.ALLOWED_TRANSITIONS.get(current_status, [])
        if new_status not in allowed_next:
            raise ValueError(f'لا يمكن تغيير الحالة من "{OrderService.status_label(current_status)}" إلى "{OrderService.status_label(new_status)}"')

        if new_status == 'delivering' and not delivery_person_id and not order.delivery_person_id:
            raise ValueError('يجب تعيين مندوب قبل بدء التسليم')

        if delivery_person_id:
            person = UserRepository.get_by_id(delivery_person_id)
            if not person:
                raise ValueError('المندوب غير موجود')
            if person.role != 'delivery':
                raise ValueError('المستخدم المحدد ليس مندوب توصيل')

            # S12: منع تغيير المندوب بعد الإسناد
            if order.delivery_person_id is not None and order.delivery_person_id != person.id:
                raise ValueError('لا يمكن تغيير المندوب بعد إسناد الطلب إليه')

            if not is_delivery_available(person):
                raise ValueError('المندوب غير متاح حالياً')
            if not order.store.has_delivery:
                raise ValueError('هذا المتجر لا يوفر خدمة توصيل')

            # أول إسناد: توليد pickup_code + احتساب رسوم التوصيل (إن لم تكن محسوبة)
            if order.delivery_person_id is None:
                if not order.delivery_fee or order.delivery_fee == 0:
                    order.delivery_fee = float(get_setting('delivery_fee', 100))
                    order.total = (order.total or 0) + order.delivery_fee
                if not order.pickup_code:
                    order.pickup_code = OrderService.generate_pickup_code()
                order.delivery_person_id = person.id
        else:
            # لا يوجد مندوب — إعادة تعيين (فقط لو ما زال غير مُسند)
            if order.delivery_person_id is None:
                if not order.delivery_address:
                    order.delivery_fee = 0.0

        if new_status == 'cancelled' and order.status != 'cancelled':
            for item in order.items:
                product = item.product
                if product:
                    product.stock_quantity += item.quantity
                    db.session.add(product)

        from_status = order.status
        order.status = new_status
        order.updated_at = current_time()
        if new_status == 'cancelled':
            order.is_cancelled = True
        elif new_status == 'delivered':
            order.delivered_at = current_time()
            payments = Payment.query.filter_by(order_id=order.id).all()
            for p in payments:
                if p.status == 'pending' and p.method == 'cash':
                    p.status = 'paid'

        OrderRepository.update_order(order)

        OrderRepository.add_status_history(
            order_id=order.id,
            from_status=from_status,
            to_status=new_status,
            changed_by=actor_id,
            note=note or f'تغيير الحالة إلى {OrderService.status_label(new_status)}'
        )

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise ValueError('حدث خطأ أثناء تحديث الطلب')

        status_ar = OrderService.status_label(new_status)

        if delivery_person_id and notify_delivery and from_status != 'delivering':
            try:
                NotificationService.send_to_user(
                    user_id=delivery_person_id,
                    message=f'تم إسناد الطلب رقم {order.id} إليك من متجر {order.store.name}',
                    title='طلب جديد لك',
                    link=url_for('delivery.delivery_dashboard'),
                    type_=NotificationService.TYPE_DELIVERY,
                    priority=NotificationService.PRIORITY_IMPORTANT
                )
            except Exception as e:
                logger.error(f'فشل إرسال إشعار للمندوب: {str(e)}')

        if order.customer_id:
            customer = UserRepository.get_by_id(order.customer_id)
            if customer:
                try:
                    NotificationService.send_to_user(
                        user_id=customer.id,
                        message=f'طلبك رقم {order.id} من متجر {order.store.name}: {status_ar}',
                        title='تحديث حالة الطلب',
                        link=url_for('cart.cart'),
                        type_=NotificationService.TYPE_ORDER
                    )
                except Exception as e:
                    logger.error(f'فشل إرسال إشعار للزبون: {str(e)}')

        return order

    @staticmethod
    def update_order_status_by_store(user, store, order, new_status,
                                     delivery_person_id=None, notify_delivery=False):
        if order.store_id != store.id:
            return None, 'هذا الطلب لا يخص متجرك'

        if not is_store_active(store):
            return None, 'متجرك غير نشط حالياً، لا يمكنك تحديث الطلبات'

        try:
            updated = OrderService._apply_status_update(
                order=order,
                new_status=new_status,
                actor_id=user.id,
                delivery_person_id=delivery_person_id,
                notify_delivery=notify_delivery
            )
            return updated, None
        except ValueError as e:
            return None, str(e)
        except Exception as e:
            logger.exception('خطأ في update_order_status_by_store')
            return None, 'حدث خطأ غير متوقع'

    @staticmethod
    def update_order_status_by_admin(order, new_status, actor_id=None):
        try:
            updated = OrderService._apply_status_update(
                order=order,
                new_status=new_status,
                actor_id=actor_id,
                note='تحديث من قبل الإدارة'
            )
            return updated, None
        except ValueError as e:
            return None, str(e)
        except Exception as e:
            logger.exception('خطأ في update_order_status_by_admin')
            return None, 'حدث خطأ غير متوقع'
