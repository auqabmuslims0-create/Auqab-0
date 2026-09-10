from datetime import datetime
from flask import render_template, request, redirect, url_for, flash
from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from models import Subscription, Store, User, Payment
from shared.services.subscription_service import SubscriptionService
from shared.decorators import role_required
from . import admin_bp


@admin_bp.route('/admin/subscriptions')
@role_required('admin')
def admin_subscriptions():
    q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()
    store_id = request.args.get('store_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = 20

    query = Subscription.query.filter(Subscription.store_id.isnot(None)).options(
        selectinload(Subscription.user),
        selectinload(Subscription.store)
    )

    if store_id:
        query = query.filter(Subscription.store_id == store_id)

    if q:
        query = query.filter(
            or_(
                Subscription.payment_ref.ilike(f'%{q}%'),
                Subscription.store.has(Store.name.ilike(f'%{q}%')),
                Subscription.user.has(User.username.ilike(f'%{q}%'))
            )
        )
    if status_filter in ['pending', 'paid', 'cancelled', 'expired', 'suspended']:
        query = query.filter(Subscription.status == status_filter)

    pagination = query.order_by(Subscription.start_date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    subs = pagination.items
    sub_ids = [sub.id for sub in subs]
    payments_map = {}
    if sub_ids:
        all_payments = Payment.query.filter(Payment.subscription_id.in_(sub_ids)).all()
        for pay in all_payments:
            payments_map.setdefault(pay.subscription_id, []).append(pay)
    return render_template('admin/admin_subscriptions.html', subs=subs, pagination=pagination,
                           q=q, status_filter=status_filter, payments_map=payments_map,
                           store_id=store_id)


@admin_bp.route('/admin/subscriptions/<int:sub_id>/approve', methods=['POST'])
@role_required('admin')
def admin_approve_subscription(sub_id):
    override_days = request.form.get('override_days', type=int)
    override_end_date_str = request.form.get('override_end_date', '').strip()
    override_amount = request.form.get('override_amount', type=float)
    admin_note = request.form.get('admin_note', '').strip() or None

    override_end_date = None
    if override_end_date_str:
        try:
            override_end_date = datetime.strptime(override_end_date_str, '%Y-%m-%d')
        except ValueError:
            flash('تاريخ الانتهاء غير صالح', 'error')
            return redirect(url_for('admin.admin_subscriptions'))

    success, msg = SubscriptionService.approve_subscription(
        sub_id,
        override_days=override_days,
        override_end_date=override_end_date,
        override_amount=override_amount,
        admin_note=admin_note
    )
    flash(msg, 'success' if success else 'error')
    return redirect(url_for('admin.admin_subscriptions'))


@admin_bp.route('/admin/subscriptions/<int:sub_id>/reject', methods=['POST'])
@role_required('admin')
def admin_reject_subscription(sub_id):
    admin_note = request.form.get('admin_note', '').strip() or None
    success, msg = SubscriptionService.reject_subscription(sub_id, admin_note=admin_note)
    flash(msg, 'success' if success else 'error')
    return redirect(url_for('admin.admin_subscriptions'))


@admin_bp.route('/admin/subscriptions/<int:sub_id>/extend', methods=['POST'])
@role_required('admin')
def admin_extend_subscription(sub_id):
    days = request.form.get('days', type=int)
    admin_note = request.form.get('admin_note', '').strip() or None
    success, msg = SubscriptionService.extend_subscription(sub_id, days=days, admin_note=admin_note)
    flash(msg, 'success' if success else 'error')
    return redirect(url_for('admin.admin_subscriptions'))


@admin_bp.route('/admin/subscriptions/<int:sub_id>/set-end', methods=['POST'])
@role_required('admin')
def admin_set_subscription_end(sub_id):
    end_date_str = request.form.get('end_date', '').strip()
    admin_note = request.form.get('admin_note', '').strip() or None

    if not end_date_str:
        flash('يرجى تحديد تاريخ الانتهاء', 'error')
        return redirect(url_for('admin.admin_subscriptions'))
    try:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    except ValueError:
        flash('تاريخ غير صالح', 'error')
        return redirect(url_for('admin.admin_subscriptions'))

    success, msg = SubscriptionService.set_subscription_end_date(sub_id, end_date, admin_note=admin_note)
    flash(msg, 'success' if success else 'error')
    return redirect(url_for('admin.admin_subscriptions'))
