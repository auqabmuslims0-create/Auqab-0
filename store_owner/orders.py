from flask import render_template, request, redirect, url_for, flash, abort
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
import sys

logger = logging.getLogger(__name__)


def _diag(msg):
    """طباعة تشخيصية للـ terminal (تنفع عند التعليق)."""
    print(f'[ORDERS-DIAG] {msg}', flush=True, file=sys.stderr)


# S12: الحالات المسموح لصاحب المتجر الانتقال إليها (بدون "delivering" — من مسؤولية المندوب)
STORE_ALLOWED_STATUSES = ['confirmed', 'preparing', 'ready', 'cancelled']


def _get_delivery_persons_stats():
    """H6: استعلام واحد بدل N+1 لحساب الطلبات النشطة لكل مندوب."""
    _diag('_get_delivery_persons_stats: start')
    persons = User.query.filter_by(role='delivery', is_active=True).order_by(User.username).all()
    _diag(f'_get_delivery_persons_stats: loaded {len(persons)} persons')
    if not persons:
        return [], {}

    person_ids = [p.id for p in persons]
    _diag(f'_get_delivery_persons_stats: counting active orders for {person_ids}')
    active_counts = dict(db.session.query(
        Order.delivery_person_id, func.count(Order.id)
    ).filter(
        Order.delivery_person_id.in_(person_ids),
        Order.status.in_(['ready', 'delivering'])
    ).group_by(Order.delivery_person_id).all())
    _diag(f'_get_delivery_persons_stats: active_counts={active_counts}')

    stats = {}
    for person in persons:
        _diag(f'_get_delivery_persons_stats: processing person {person.id} ({person.username})')
        try:
            is_avail = is_delivery_available(person)
        except Exception as e:
            _diag(f'ERROR in is_delivery_available for {person.id}: {e}')
            is_avail = False
        stats[person.id] = {
            'active_orders': active_counts.get(person.id, 0),
            'is_available': is_avail,
            'shift_start': person.shift_start_time.strftime('%H:%M') if person.shift_start_time else None,
            'shift_end': person.shift_end_time.strftime('%H:%M') if person.shift_end_time else None,
        }
    _diag(f'_get_delivery_persons_stats: done')
    return persons, stats


@store_bp.route('/store/<int:store_id>/orders')
@role_required('owner')
def store_orders(store_id):
    _diag(f'=== store_orders START store_id={store_id} ===')
    result = check_store_access(store_id)
    if result[0] is None:
        _diag('check_store_access returned None (redirect)')
        return result[1]
    user, store = result
    _diag(f'check_store_access OK: user={user.id} store={store.id}')

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
    _diag('before paginate')
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    orders = pagination.items
    _diag(f'after paginate: {len(orders)} orders, total={pagination.total} pages={pagination.pages}')

    # S12: قائمة المندوبين + إحصائياتهم
    _diag('before _get_delivery_persons_stats')
    delivery_persons, delivery_person_stats = _get_delivery_persons_stats()
    _diag(f'after _get_delivery_persons_stats: {len(delivery_persons)} persons')

    _diag('before render_template')
    resp = render_template('store_owner/store_orders.html',
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
    _diag('after render_template — DONE')
    return resp


@store_bp.route('/store/<int:store_id>/orders/<int:order_id>/status', methods=['POST'])
@role_required('owner')
def update_order_status(store_id, order_id):
    _diag(f'=== update_order_status START order_id={order_id} ===')
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    _diag(f'update_order_status: new_status={new_status}')

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
        _diag(f'update_order_status ERROR: {error}')
        flash(error, 'error')
    else:
        _diag(f'update_order_status OK')
        flash('تم تحديث حالة الطلب', 'success')
    return redirect(url_for('store.store_orders', store_id=store.id))


@store_bp.route('/store/<int:store_id>/orders/<int:order_id>/assign-delivery', methods=['POST'])
@role_required('owner')
def assign_delivery(store_id, order_id):
    """S12 + S13: إسناد مندوب لطلب جاهز للتسليم."""
    _diag(f'=== assign_delivery START order_id={order_id} ===')
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    order = Order.query.get_or_404(order_id)

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

    try:
        order.delivery_person_id = person.id
        if not order.pickup_code:
            order.pickup_code = OrderService.generate_pickup_code()
        if not order.delivery_fee or order.delivery_fee == 0:
            order.delivery_fee = float(get_setting('delivery_fee', 100))
            order.total = (order.total or 0) + order.delivery_fee
        order.updated_at = current_time()
        db.session.add(order)

        history = OrderStatusHistory(
            order_id=order.id,
            from_status=order.status,
            to_status=order.status,
            changed_by=user.id,
            note=f'تم إسناد الطلب للمندوب {person.username}'
        )
        db.session.add(history)

        db.session.commit()
        _diag(f'assign_delivery: DB committed')
    except Exception as e:
        db.session.rollback()
        _diag(f'assign_delivery ERROR: {e}')
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
        _diag('assign_delivery: notification sent to delivery')
    except Exception as e:
        _diag(f'assign_delivery notification error: {e}')

    if order.customer_id:
        try:
            NotificationService.send_to_user(
                user_id=order.customer_id,
                message=f'طلبك رقم {order.id} في طريقه إليك مع المندوب {person.username}',
                title='طلبك في الطريق',
                link=url_for('cart.cart'),
                type_=NotificationService.TYPE_ORDER
            )
            _diag('assign_delivery: notification sent to customer')
        except Exception as e:
            _diag(f'assign_delivery customer notification error: {e}')

    flash(f'تم إسناد الطلب للمندوب {person.username}', 'success')
    return redirect(url_for('store.store_orders', store_id=store.id))
