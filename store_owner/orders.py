from flask import render_template, request, redirect, url_for, flash
from database import db
from models import User, Order, OrderItem, OrderStatusHistory
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from shared.time_utils import current_time
from shared.delivery_utils import is_delivery_available
from shared.decorators import role_required
from shared.services.order_service import OrderService
from shared.services.notification_service import NotificationService
from shared.utils import get_setting
from . import store_bp
from .common import check_store_access
import logging

logger = logging.getLogger(__name__)


# S12: الحالات المسموح لصاحب المتجر الانتقال إليها (بدون "delivering" — من مسؤولية المندوب)
STORE_ALLOWED_STATUSES = ['confirmed', 'preparing', 'ready', 'cancelled']


def _get_delivery_persons_stats():
    """H6: استعلام واحد بدل N+1 لحساب الطلبات النشطة لكل مندوب."""
    persons = User.query.filter_by(role='delivery', is_active=True).order_by(User.username).all()
    if not persons:
        return [], {}

    person_ids = [p.id for p in persons]
    active_counts = dict(db.session.query(
        Order.delivery_person_id, func.count(Order.id)
    ).filter(
        Order.delivery_person_id.in_(person_ids),
        Order.status.in_(['ready', 'delivering'])
    ).group_by(Order.delivery_person_id).all())

    stats = {}
    for person in persons:
        try:
            is_avail = is_delivery_available(person)
        except Exception as e:
            logger.error(f'is_delivery_available failed for {person.id}: {e}')
            is_avail = False
        stats[person.id] = {
            'active_orders': active_counts.get(person.id, 0),
            'is_available': is_avail,
            'shift_start': person.shift_start_time.strftime('%H:%M') if person.shift_start_time else None,
            'shift_end': person.shift_end_time.strftime('%H:%M') if person.shift_end_time else None,
        }
    return persons, stats


@store_bp.route('/store/<int:store_id>/orders')
@role_required('owner')
def store_orders(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    status_filter = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 10

    allowed_statuses = ['new', 'confirmed', 'preparing', 'ready', 'delivering', 'delivered', 'cancelled']

    query = Order.query.filter_by(store_id=store.id).options(
        selectinload(Order.items).selectinload(OrderItem.product),
        selectinload(Order.delivery_person),
        selectinload(Order.customer)
    )
    if status_filter in allowed_statuses:
        query = query.filter(Order.status == status_filter)

    query = query.order_by(Order.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    orders = pagination.items

    # S12: قائمة المندوبين + إحصائياتهم
    delivery_persons, delivery_person_stats = _get_delivery_persons_stats()

    return render_template('store_owner/store_orders.html',
                           store=store,
                           orders=orders,
                           pagination=pagination,
                           delivery_persons=delivery_persons,
                           delivery_person_stats=delivery_person_stats,
                           status_filter=status_filter,
                           allowed_statuses=allowed_statuses,
                           store_allowed_statuses=STORE_ALLOWED_STATUSES,
                           allowed_transitions=OrderService.ALLOWED_TRANSITIONS,
                           status_labels=OrderService.STATUS_LABELS)


@store_bp.route('/store/<int:store_id>/orders/<int:order_id>/status', methods=['POST'])
@role_required('owner')
def update_order_status(store_id, order_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    order = db.get_or_404(Order, order_id)
    new_status = request.form.get('status')

    if new_status not in STORE_ALLOWED_STATUSES:
        flash('هذه الحالة غير مسموح بها من قبل صاحب المتجر', 'error')
        return redirect(url_for('store.store_orders', store_id=store.id))

    updated_order, error = OrderService.update_order_status_by_store(
        user=user,
        store=store,
        order=order,
        new_status=new_status,
        delivery_person_id=None,
        notify_delivery=False
    )

    if error:
        flash(error, 'error')
    else:
        flash('تم تحديث حالة الطلب', 'success')
    return redirect(url_for('store.store_orders', store_id=store.id))


@store_bp.route('/store/<int:store_id>/orders/<int:order_id>/assign-delivery', methods=['POST'])
@role_required('owner')
def assign_delivery(store_id, order_id):
    """S12 + S13: إسناد مندوب لطلب جاهز للتسليم (بشكل ذرّي)."""
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    order = db.get_or_404(Order, order_id)

    if order.store_id != store.id:
        flash('هذا الطلب لا يخص متجرك', 'error')
        return redirect(url_for('store.store_orders', store_id=store.id))

    if order.status != 'ready':
        flash('يمكن إسناد مندوب فقط للطلبات الجاهزة للتسليم', 'error')
        return redirect(url_for('store.store_orders', store_id=store.id))

    if order.delivery_person_id is not None:
        flash('تم إسناد هذا الطلب لمندوب مسبقاً، لا يمكن التغيير', 'error')
        return redirect(url_for('store.store_orders', store_id=store.id))

    if not store.has_delivery:
        flash('هذا المتجر لا يوفر خدمة توصيل', 'error')
        return redirect(url_for('store.store_orders', store_id=store.id))

    delivery_person_id = request.form.get('delivery_person_id', type=int)
    if not delivery_person_id:
        flash('يرجى اختيار مندوب', 'error')
        return redirect(url_for('store.store_orders', store_id=store.id))

    person = db.session.get(User, delivery_person_id)
    if not person or person.role != 'delivery' or not person.is_active:
        flash('المندوب غير موجود أو غير نشط', 'error')
        return redirect(url_for('store.store_orders', store_id=store.id))

    if not is_delivery_available(person):
        flash('المندوب غير متاح حالياً', 'error')
        return redirect(url_for('store.store_orders', store_id=store.id))

    # ===== إسناد ذرّي =====
    pickup_code = order.pickup_code or OrderService.generate_pickup_code()
    fee_was_zero = not order.delivery_fee or order.delivery_fee == 0
    default_fee = float(get_setting('delivery_fee', 100))
    new_fee = default_fee if fee_was_zero else order.delivery_fee
    new_total = (order.total or 0) + (default_fee if fee_was_zero else 0)

    try:
        updated = Order.query.filter(
            Order.id == order_id,
            Order.delivery_person_id.is_(None),
            Order.status == 'ready'
        ).update({
            'delivery_person_id': person.id,
            'pickup_code': pickup_code,
            'delivery_fee': new_fee,
            'total': new_total,
            'updated_at': current_time(),
        }, synchronize_session=False)

        if updated == 0:
            db.session.rollback()
            flash('تم إسناد الطلب لمندوب آخر قبلك', 'error')
            return redirect(url_for('store.store_orders', store_id=store.id))

        history = OrderStatusHistory(
            order_id=order_id,
            from_status='ready',
            to_status='ready',
            changed_by=user.id,
            note=f'تم إسناد الطلب للمندوب {person.username}'
        )
        db.session.add(history)
        db.session.commit()
        db.session.refresh(order)
    except Exception:
        db.session.rollback()
        logger.exception('assign_delivery: DB commit failed')
        flash('حدث خطأ أثناء الإسناد', 'error')
        return redirect(url_for('store.store_orders', store_id=store.id))

    # إشعارات
    try:
        NotificationService.send_to_user(
            user_id=person.id,
            message=f'تم إسناد الطلب رقم {order.id} إليك من متجر {store.name}',
            title='طلب جديد لك',
            link=url_for('delivery.delivery_dashboard'),
            type_=NotificationService.TYPE_DELIVERY,
            priority=NotificationService.PRIORITY_IMPORTANT
        )
    except Exception as e:
        logger.error(f'assign_delivery notification (delivery) failed: {e}')

    if order.customer_id:
        try:
            NotificationService.send_to_user(
                user_id=order.customer_id,
                message=f'طلبك رقم {order.id} في طريقه إليك مع المندوب {person.username}',
                title='طلبك في الطريق',
                link=url_for('cart.cart'),
                type_=NotificationService.TYPE_ORDER
            )
        except Exception as e:
            logger.error(f'assign_delivery notification (customer) failed: {e}')

    flash(f'تم إسناد الطلب للمندوب {person.username}', 'success')
    return redirect(url_for('store.store_orders', store_id=store.id))
