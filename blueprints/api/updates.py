from flask import jsonify, session
from sqlalchemy import func
from database import db
from models import User, Order, Store, Subscription, Notification, Product
from shared.decorators import login_required
from shared.services.notification_service import NotificationService
from . import api_bp


@api_bp.route('/updates')
@login_required
def get_updates():
    user_id = session.get('user_id')
    user = db.session.get(User, user_id) if user_id else None
    if not user:
        return jsonify({'error': 'unauthorized'}), 401

    data = {
        'unread_notifications': 0,
        'latest_notification_id': 0,
        'new_orders_count': 0,
        'latest_new_order_id': 0,
        'delivery_new_orders_count': 0,
        'admin_pending_subscriptions': 0,
        'cart_count': 0,
        'latest_market_product_id': 0,
    }

    # آخر إشعار (لعموم المستخدمين) + عدّاد غير المقروء
    latest_notif_id = (
        db.session.query(func.max(Notification.id))
        .filter(Notification.user_id == user.id)
        .scalar()
    )
    data['latest_notification_id'] = latest_notif_id or 0
    data['unread_notifications'] = NotificationService.get_unread_count(user.id)

    # سلة
    cart = session.get('cart', {})
    if isinstance(cart, dict):
        try:
            data['cart_count'] = sum(int(v) for v in cart.values())
        except (TypeError, ValueError):
            data['cart_count'] = 0

    # صاحب المتجر — آخر طلب جديد لطلب يحتاج إجراء
    if user.role == 'owner':
        stores = Store.query.filter_by(owner_id=user.id).all()
        store_ids = [s.id for s in stores]
        if store_ids:
            data['new_orders_count'] = Order.query.filter(
                Order.store_id.in_(store_ids),
                Order.status == 'new'
            ).count()
            latest_order_id = (
                db.session.query(func.max(Order.id))
                .filter(Order.store_id.in_(store_ids), Order.status == 'new')
                .scalar()
            )
            data['latest_new_order_id'] = latest_order_id or 0

    elif user.role == 'delivery':
        data['delivery_new_orders_count'] = Order.query.filter_by(
            delivery_person_id=user.id,
            status='ready'
        ).count()

    elif user.role == 'admin':
        data['admin_pending_subscriptions'] = Subscription.query.filter_by(
            status='pending'
        ).count()

    # آخر منتج معروض في السوق (من متاجر نشطة) — لعموم المستخدمين
    latest_product_id = (
        db.session.query(func.max(Product.id))
        .join(Store, Store.id == Product.store_id)
        .filter(Store.subscription_status == 'active')
        .scalar()
    )
    data['latest_market_product_id'] = latest_product_id or 0

    return jsonify(data)
