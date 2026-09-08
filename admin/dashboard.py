from flask import render_template, session, redirect, url_for
from sqlalchemy import func
from database import db
from models import User, Store, Order, Subscription, Payment
from shared.decorators import role_required
from . import admin_bp

@admin_bp.route('/admin')
@role_required('admin')
def admin_dashboard():
    from shared.services.subscription_service import SubscriptionService
    SubscriptionService.check_expiring_subscriptions()

    total_users = User.query.count()
    total_stores = Store.query.count()
    total_orders = Order.query.count()
    pending_subscriptions = Subscription.query.filter_by(status='pending').count()
    delivery_persons_count = User.query.filter_by(role='delivery').count()
    assigned_orders_count = Order.query.filter(Order.delivery_person_id.isnot(None)).count()
    delivery_fee_total = db.session.query(func.sum(Order.delivery_fee)).filter(
        Order.status != 'cancelled'
    ).scalar() or 0

    total_paid_payments = db.session.query(func.sum(Payment.amount)).filter(
        Payment.status == 'paid'
    ).scalar() or 0
    pending_payments_count = Payment.query.filter_by(status='pending').count()

    return render_template('admin/admin_dashboard.html',
                           total_users=total_users,
                           total_stores=total_stores,
                           total_orders=total_orders,
                           pending_subscriptions=pending_subscriptions,
                           delivery_persons_count=delivery_persons_count,
                           assigned_orders_count=assigned_orders_count,
                           delivery_fee_total=delivery_fee_total,
                           total_paid_payments=total_paid_payments,
                           pending_payments_count=pending_payments_count)
