from flask import jsonify, session
from database import db
from models import User, Order, Store, Subscription, Notification
from shared.decorators import login_required
from . import api_bp
from shared.services.notification_service import NotificationService

@api_bp.route('/updates')
@login_required
def get_updates():
    user_id = session.get('user_id')
    user = db.session.get(User, user_id) if user_id else None
    if not user:
        return jsonify({'error': 'unauthorized'}), 401

    data = {
        'unread_notifications': 0,
        'new_orders_count': 0,
        'delivery_new_orders_count': 0,
        'admin_pending_subscriptions': 0,
        'cart_count': 0
    }

    # استخدام NotificationService للحصول على العدد
    data['unread_notifications'] = NotificationService.get_unread_count(user.id)

    cart = session.get('cart', {})
    if isinstance(cart, dict):
        data['cart_count'] = sum(cart.values())

    if user.role == 'owner':
        stores = Store.query.filter_by(owner_id=user.id).all()
        store_ids = [s.id for s in stores]
        if store_ids:
            data['new_orders_count'] = Order.query.filter(
                Order.store_id.in_(store_ids),
                Order.status == 'new'
            ).count()

    elif user.role == 'delivery':
        data['delivery_new_orders_count'] = Order.query.filter_by(
            delivery_person_id=user.id,
            status='ready'
        ).count()

    elif user.role == 'admin':
        data['admin_pending_subscriptions'] = Subscription.query.filter_by(
            status='pending'
        ).count()

    return jsonify(data)
