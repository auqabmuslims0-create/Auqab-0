from flask import render_template, request, redirect, url_for, flash, session
from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from database import db
from models import Order, OrderItem, Store, User
from shared.services.order_service import OrderService
from shared.decorators import role_required
from . import admin_bp

@admin_bp.route('/admin/orders')
@role_required('admin')
def admin_orders():
    q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20

    query = Order.query.options(
        selectinload(Order.customer),
        selectinload(Order.store),
        selectinload(Order.items).selectinload(OrderItem.product),
        selectinload(Order.delivery_person)
    )

    if q:
        if q.isdigit():
            query = query.filter(Order.id == int(q))
        else:
            query = query.filter(
                or_(
                    Order.customer.has(User.username.ilike(f'%{q}%')),
                    Order.store.has(Store.name.ilike(f'%{q}%'))
                )
            )

    allowed_statuses = ['new', 'confirmed', 'preparing', 'ready', 'delivering', 'delivered', 'cancelled']
    if status_filter in allowed_statuses:
        query = query.filter(Order.status == status_filter)

    pagination = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    orders = pagination.items

    grouped = {}
    for order in orders:
        store_id = order.store_id
        if store_id not in grouped:
            grouped[store_id] = {
                'store': order.store,
                'orders': [],
                'total_count': 0,
                'total_amount': 0.0
            }
        grouped[store_id]['orders'].append(order)
        grouped[store_id]['total_count'] += 1
        grouped[store_id]['total_amount'] += order.total

    grouped_list = list(grouped.values())
    grouped_list.sort(key=lambda g: g['store'].name if g['store'] else '')

    return render_template('admin/admin_orders.html', grouped_orders=grouped_list,
                           pagination=pagination, q=q, status_filter=status_filter,
                           allowed_statuses=allowed_statuses)

@admin_bp.route('/admin/orders/<int:order_id>/status', methods=['POST'])
@role_required('admin')
def admin_update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    allowed_statuses = ['new', 'confirmed', 'preparing', 'ready', 'delivering', 'delivered', 'cancelled']
    if new_status not in allowed_statuses:
        flash('حالة غير صالحة', 'error')
        return redirect(url_for('admin.admin_orders'))

    updated, error = OrderService.update_order_status_by_admin(
        order,
        new_status,
        actor_id=session.get('user_id')
    )
    if error:
        flash(error, 'error')
    else:
        flash('تم تحديث حالة الطلب بنجاح', 'success')
    return redirect(url_for('admin.admin_orders'))
