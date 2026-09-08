from flask import render_template
from sqlalchemy import func
from database import db
from models import User, Store, Order, Subscription, Payment
from shared.decorators import role_required
from . import admin_bp

@admin_bp.route('/admin/finance')
@role_required('admin')
def admin_finance():
    subscription_revenue = db.session.query(func.sum(Subscription.amount)).filter(
        Subscription.status == 'paid'
    ).scalar() or 0

    paid_subscriptions = Subscription.query.filter_by(status='paid').count()

    order_revenue = db.session.query(func.sum(Order.total)).filter(
        Order.status != 'cancelled'
    ).scalar() or 0

    total_orders = Order.query.filter(Order.status != 'cancelled').count()

    delivery_fee_revenue = db.session.query(func.sum(Order.delivery_fee)).filter(
        Order.status != 'cancelled'
    ).scalar() or 0

    delivered_orders_count = Order.query.filter(Order.delivery_person_id.isnot(None)).count()

    total_users = User.query.count()
    total_stores = Store.query.count()
    active_stores = Store.query.filter_by(subscription_status='active').count()
    pending_subscriptions = Subscription.query.filter_by(status='pending').count()

    user_role_counts = db.session.query(
        User.role, func.count(User.id).label('count')
    ).group_by(User.role).all()

    order_status_counts = db.session.query(
        Order.status, func.count(Order.id).label('count')
    ).group_by(Order.status).all()

    total_payments = db.session.query(func.sum(Payment.amount)).filter(Payment.status == 'paid').scalar() or 0

    return render_template(
        'admin/admin_finance.html',
        subscription_revenue=subscription_revenue,
        paid_subscriptions=paid_subscriptions,
        order_revenue=order_revenue,
        total_orders=total_orders,
        total_users=total_users,
        total_stores=total_stores,
        active_stores=active_stores,
        pending_subscriptions=pending_subscriptions,
        user_role_counts=user_role_counts,
        order_status_counts=order_status_counts,
        delivery_fee_revenue=delivery_fee_revenue,
        delivered_orders_count=delivered_orders_count,
        total_payments=total_payments
    )
