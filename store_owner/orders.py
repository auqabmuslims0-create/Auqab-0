from flask import render_template, request, redirect, url_for, flash, abort
from database import db
from models import User, Order, OrderItem
from datetime import timedelta
from sqlalchemy.orm import selectinload
from shared.time_utils import current_time
from shared.delivery_utils import is_delivery_available
from shared.decorators import role_required
from shared.services.order_service import OrderService
from . import store_bp
from .common import check_store_access

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

    all_delivery_persons = User.query.filter_by(role='delivery').all()
    delivery_persons = [p for p in all_delivery_persons if is_delivery_available(p)]

    delivery_person_stats = {}
    for person in delivery_persons:
        active_orders = Order.query.filter(
            Order.delivery_person_id == person.id,
            Order.status.in_(['ready', 'delivering'])
        ).count()
        delivery_person_stats[person.id] = {
            'active_orders': active_orders,
            'is_busy': active_orders > 0
        }

    return render_template('store_owner/store_orders.html',
                           store=store,
                           orders=orders,
                           pagination=pagination,
                           delivery_persons=delivery_persons,
                           delivery_person_stats=delivery_person_stats,
                           status_filter=status_filter,
                           allowed_statuses=allowed_statuses)

@store_bp.route('/store/<int:store_id>/orders/<int:order_id>/status', methods=['POST'])
@role_required('owner')
def update_order_status(store_id, order_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    delivery_person_id = request.form.get('delivery_person_id', type=int)
    notify_delivery = request.form.get('notify_delivery') == 'yes'

    updated_order, error = OrderService.update_order_status_by_store(
        user=user,
        store=store,
        order=order,
        new_status=new_status,
        delivery_person_id=delivery_person_id,
        notify_delivery=notify_delivery
    )

    if error:
        flash(error, 'error')
    else:
        flash('تم تحديث حالة الطلب', 'success')
    return redirect(url_for('store.store_orders', store_id=store.id))
