from flask import render_template, request, redirect, url_for, flash
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload
from database import db
from models import Store, User, Product, Order
from shared.services.store_service import StoreService
from shared.decorators import role_required
from shared.time_utils import current_time
from . import admin_bp

@admin_bp.route('/admin/stores')
@role_required('admin')
def admin_stores():
    q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 12

    query = Store.query.options(selectinload(Store.owner))
    if q:
        query = query.filter(
            or_(
                Store.name.ilike(f'%{q}%'),
                Store.owner.has(User.username.ilike(f'%{q}%')),
                Store.owner.has(User.email.ilike(f'%{q}%'))
            )
        )
    if status_filter in ['active', 'pending', 'suspended', 'cancelled', 'expired']:
        query = query.filter_by(subscription_status=status_filter)

    pagination = query.order_by(Store.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    stores = pagination.items
    now = current_time()
    for store in stores:
        if store.pending_deletion_at:
            remaining = (store.pending_deletion_at - now).total_seconds()
            store.delete_remaining_seconds = max(0, int(remaining))
        else:
            store.delete_remaining_seconds = None

    store_stats = {}
    if stores:
        store_ids = [s.id for s in stores]
        product_counts = dict(db.session.query(
            Product.store_id, func.count(Product.id)
        ).filter(Product.store_id.in_(store_ids)).group_by(Product.store_id).all())

        order_counts = dict(db.session.query(
            Order.store_id, func.count(Order.id)
        ).filter(Order.store_id.in_(store_ids)).group_by(Order.store_id).all())

        for s in stores:
            store_stats[s.id] = {
                'products_count': product_counts.get(s.id, 0),
                'orders_count': order_counts.get(s.id, 0),
            }

    return render_template('admin/admin_stores.html', stores=stores, pagination=pagination,
                           q=q, status_filter=status_filter, store_stats=store_stats)

@admin_bp.route('/admin/stores/<int:store_id>/toggle', methods=['POST'])
@role_required('admin')
def admin_toggle_store(store_id):
    action = request.form.get('action', '').strip()
    if action == 'activate':
        success, msg, _ = StoreService.toggle_store_status(store_id, force_activate=True)
    elif action == 'suspend':
        success, msg, _ = StoreService.toggle_store_status(store_id, force_activate=False)
    else:
        store = Store.query.get_or_404(store_id)
        if store.subscription_status == 'active':
            success, msg, _ = StoreService.toggle_store_status(store_id, force_activate=False)
        else:
            success, msg, _ = StoreService.toggle_store_status(store_id, force_activate=True)
    flash(msg, 'success' if success else 'error')
    return redirect(url_for('admin.admin_stores'))
