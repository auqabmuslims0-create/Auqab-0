from flask import render_template, request, redirect, url_for, flash, abort
from database import db
from models import Subscription
from shared.time_utils import current_time
from shared.utils import is_store_active, get_setting
from shared.decorators import role_required
from shared.services.subscription_service import SubscriptionService
from . import store_bp
from .common import check_store_access

@store_bp.route('/store/<int:store_id>/subscription')
@role_required('owner')
def store_subscription(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    subscription_price = float(get_setting('subscription_price', 500))
    duration_days = int(get_setting('subscription_duration_days', 30))
    wallet_number = get_setting('wallet_number', '0995680223')

    sub = Subscription.query.filter_by(store_id=store.id) \
        .order_by(Subscription.start_date.desc()).first()

    if sub and sub.status == 'paid' and sub.end_date > current_time():
        return render_template('store_owner/store_subscription.html', store=store, sub=sub,
                               subscription_price=subscription_price, wallet_number=wallet_number,
                               active=True, duration_days=duration_days)

    if sub and sub.status == 'pending':
        return redirect(url_for('store.subscription_pending', store_id=store.id))

    return render_template('store_owner/store_subscription.html', store=store, sub=sub,
                           subscription_price=subscription_price, wallet_number=wallet_number,
                           active=False, duration_days=duration_days)

@store_bp.route('/store/<int:store_id>/subscription/method/<method>', methods=['GET', 'POST'])
@role_required('owner')
def store_subscription_method(store_id, method):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    if method not in ['wallet', 'bank_transfer', 'manual_delivery']:
        abort(404)

    subscription_price = float(get_setting('subscription_price', 500))
    wallet_number = get_setting('wallet_number', '0995680223')

    if method in ['wallet', 'bank_transfer']:
        return render_template('store_owner/subscription_unavailable.html', store=store, method=method)

    if request.method == 'GET':
        return render_template('store_owner/subscription_manual.html', store=store,
                               wallet_number=wallet_number, subscription_price=subscription_price)

    success, msg, sub = SubscriptionService.submit_subscription_request(
        user=user, store=store, payment_ref=None, proof_file=None, payment_method='manual_delivery'
    )
    if success:
        flash(msg, 'success')
        return redirect(url_for('store.subscription_pending', store_id=store.id))
    else:
        flash(msg, 'error')
        return redirect(url_for('store.store_subscription_method', store_id=store.id, method='manual_delivery'))

@store_bp.route('/store/<int:store_id>/subscription/pending')
@role_required('owner')
def subscription_pending(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    sub = Subscription.query.filter_by(store_id=store.id, status='pending') \
        .order_by(Subscription.start_date.desc()).first()
    if not sub:
        return redirect(url_for('store.store_subscription', store_id=store.id))

    subscription_price = sub.amount
    wallet_number = get_setting('wallet_number', '0995680223')
    return render_template('store_owner/subscription_pending.html', store=store, sub=sub,
                           subscription_price=subscription_price, wallet_number=wallet_number)

@store_bp.route('/store/<int:store_id>/subscription/confirm', methods=['POST'])
@role_required('owner')
def subscription_confirm(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    sub = Subscription.query.filter_by(store_id=store.id, status='pending') \
        .order_by(Subscription.start_date.desc()).first()
    if not sub:
        flash('لا يوجد اشتراك معلق', 'error')
        return redirect(url_for('store.subscription_pending', store_id=store.id))

    code = request.form.get('confirmation_code', '').strip()
    if not code:
        flash('يرجى إدخال كود التأكيد', 'error')
        return redirect(url_for('store.subscription_pending', store_id=store.id))

    success, msg = SubscriptionService.verify_manual_confirmation(user, sub.id, code)
    if success:
        flash(msg, 'success')
        return redirect(url_for('store.store_manage', store_id=store.id))
    else:
        flash(msg, 'error')
        return redirect(url_for('store.subscription_pending', store_id=store.id))
