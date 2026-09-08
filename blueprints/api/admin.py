from shared.time_utils import current_time
from flask import request, jsonify, url_for
from sqlalchemy import func, or_
from database import db
from models import User, Store, Order, Subscription, ChatMessage
from shared.services.user_service import UserService
from shared.services.store_service import StoreService
from shared.services.subscription_service import SubscriptionService
from shared.services.delivery_service import DeliveryService
from . import api_bp
from .helpers import token_required, serialize_user, serialize_store, serialize_order

def is_admin(user):
    return user.role == 'admin'

@api_bp.route('/admin/stats', methods=['GET'])
@token_required
def admin_stats(current_user):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    total_users = User.query.count()
    total_stores = Store.query.count()
    total_orders = Order.query.count()
    pending_subscriptions = Subscription.query.filter_by(status='pending').count()
    delivery_persons_count = User.query.filter_by(role='delivery').count()
    delivery_fee_total = db.session.query(func.sum(Order.delivery_fee)).scalar() or 0
    return jsonify({
        'total_users': total_users,
        'total_stores': total_stores,
        'total_orders': total_orders,
        'pending_subscriptions': pending_subscriptions,
        'delivery_persons_count': delivery_persons_count,
        'delivery_fee_total': delivery_fee_total
    }), 200

@api_bp.route('/admin/users', methods=['GET'])
@token_required
def admin_get_users(current_user):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    role = request.args.get('role')
    q = request.args.get('q')
    query = User.query
    if role:
        query = query.filter_by(role=role)
    if q:
        query = query.filter(or_(
            User.username.ilike(f'%{q}%'),
            User.email.ilike(f'%{q}%'),
            User.phone.ilike(f'%{q}%')
        ))
    users = query.all()
    return jsonify({'users': [serialize_user(u) for u in users]}), 200

@api_bp.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@token_required
def admin_toggle_user(current_user, user_id):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    success, msg, user = UserService.toggle_user_status(user_id, admin_user_id=current_user.id)
    if not success:
        return jsonify({'message': msg}), 400
    return jsonify({'message': msg, 'is_active': user.is_active}), 200

@api_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@token_required
def admin_delete_user(current_user, user_id):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    success, msg = UserService.delete_user_fully(user_id, admin_user_id=current_user.id)
    if not success:
        return jsonify({'message': msg}), 400
    return jsonify({'message': msg}), 200

@api_bp.route('/admin/users/<int:user_id>/reset_password', methods=['POST'])
@token_required
def admin_reset_password(current_user, user_id):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    success, msg, temp_password = UserService.reset_password(user_id)
    if not success:
        return jsonify({'message': msg}), 400
    return jsonify({'message': msg, 'temp_password': temp_password}), 200

@api_bp.route('/admin/stores', methods=['GET'])
@token_required
def admin_get_stores(current_user):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    status = request.args.get('status')
    q = request.args.get('q')
    query = Store.query
    if status:
        query = query.filter_by(subscription_status=status)
    if q:
        query = query.join(User, Store.owner_id == User.id).filter(or_(
            Store.name.ilike(f'%{q}%'),
            User.username.ilike(f'%{q}%')
        ))
    stores = query.all()
    return jsonify({'stores': [serialize_store(s) for s in stores]}), 200

@api_bp.route('/admin/stores/<int:store_id>/toggle', methods=['POST'])
@token_required
def admin_toggle_store(current_user, store_id):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    success, msg, store = StoreService.toggle_store_status(store_id)
    if not success:
        return jsonify({'message': msg}), 400
    return jsonify({'message': msg, 'subscription_status': store.subscription_status}), 200

@api_bp.route('/admin/orders', methods=['GET'])
@token_required
def admin_get_orders(current_user):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    status = request.args.get('status')
    q = request.args.get('q')
    query = Order.query
    if status:
        query = query.filter_by(status=status)
    if q:
        if q.isdigit():
            query = query.filter(Order.id == int(q))
        else:
            query = query.join(User, Order.customer_id == User.id).join(Store, Order.store_id == Store.id).filter(or_(
                User.username.ilike(f'%{q}%'),
                Store.name.ilike(f'%{q}%')
            ))
    orders = query.order_by(Order.created_at.desc()).all()
    return jsonify({'orders': [serialize_order(o) for o in orders]}), 200

@api_bp.route('/admin/orders/<int:order_id>/status', methods=['POST'])
@token_required
def admin_update_order_status(current_user, order_id):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    order = Order.query.get_or_404(order_id)
    data = request.get_json(silent=True) or {}
    new_status = data.get('status')
    if new_status not in ['new', 'confirmed', 'preparing', 'ready', 'delivering', 'delivered', 'cancelled']:
        return jsonify({'message': 'حالة غير صالحة'}), 400

    if new_status == 'cancelled' and order.status != 'cancelled':
        for item in order.items:
            product = item.product
            if product:
                product.stock_quantity += item.quantity
                db.session.add(product)

    order.status = new_status
    if new_status == 'cancelled':
        order.is_cancelled = True
    elif new_status == 'delivered':
        order.delivered_at = current_time()
    db.session.commit()
    return jsonify({'message': 'تم تحديث حالة الطلب'}), 200

@api_bp.route('/admin/subscriptions', methods=['GET'])
@token_required
def admin_get_subscriptions(current_user):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    status = request.args.get('status')
    query = Subscription.query
    if status:
        query = query.filter_by(status=status)
    subs = query.all()
    subs_data = []
    for sub in subs:
        subs_data.append({
            'id': sub.id,
            'store_id': sub.store_id,
            'user_id': sub.user_id,
            'amount': sub.amount,
            'status': sub.status,
            'payment_ref': sub.payment_ref,
            'proof_image': url_for('static', filename='uploads/' + sub.proof_image, _external=True) if sub.proof_image else None,
            'start_date': sub.start_date.strftime('%Y-%m-%d') if sub.start_date else None,
            'end_date': sub.end_date.strftime('%Y-%m-%d') if sub.end_date else None
        })
    return jsonify({'subscriptions': subs_data}), 200

@api_bp.route('/admin/subscriptions/<int:sub_id>/approve', methods=['POST'])
@token_required
def admin_approve_subscription(current_user, sub_id):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    success, msg = SubscriptionService.approve_subscription(sub_id)
    if not success:
        return jsonify({'message': msg}), 400
    return jsonify({'message': msg}), 200

@api_bp.route('/admin/subscriptions/<int:sub_id>/reject', methods=['POST'])
@token_required
def admin_reject_subscription(current_user, sub_id):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    success, msg = SubscriptionService.reject_subscription(sub_id)
    if not success:
        return jsonify({'message': msg}), 400
    return jsonify({'message': msg}), 200

@api_bp.route('/admin/delivery_persons', methods=['GET'])
@token_required
def admin_get_delivery_persons(current_user):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    persons = User.query.filter_by(role='delivery').all()
    return jsonify({'persons': [serialize_user(u) for u in persons]}), 200

@api_bp.route('/admin/delivery_persons', methods=['POST'])
@token_required
def admin_create_delivery_person(current_user):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    data = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    password = data.get('password', '')

    if not username or not email or not password:
        return jsonify({'message': 'اسم المستخدم والبريد وكلمة المرور مطلوبة'}), 400

    from shared.validators import is_strong_password, is_valid_email, is_valid_phone_syrian
    from shared.utils import generate_public_id
    from werkzeug.security import generate_password_hash

    strong, msg = is_strong_password(password)
    if not strong:
        return jsonify({'message': msg}), 400

    if not is_valid_email(email):
        return jsonify({'message': 'البريد الإلكتروني غير صالح'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'message': 'اسم المستخدم موجود مسبقاً'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'message': 'البريد الإلكتروني مستخدم بالفعل'}), 400

    if phone and not is_valid_phone_syrian(phone):
        return jsonify({'message': 'رقم الهاتف يجب أن يبدأ بـ 9 ويتكون من 9 أرقام'}), 400

    public_id = generate_public_id()
    full_phone = '+963' + phone if phone else ''
    user = User(
        username=username,
        email=email,
        phone=full_phone,
        password_hash=generate_password_hash(password),
        role='delivery',
        public_id=public_id
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'تم إنشاء المندوب بنجاح', 'user': serialize_user(user)}), 201

@api_bp.route('/admin/delivery_persons/<int:user_id>/toggle', methods=['POST'])
@token_required
def admin_toggle_delivery_person(current_user, user_id):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    success, msg, user = DeliveryService.toggle_delivery_person(user_id)
    if not success:
        return jsonify({'message': msg}), 400
    return jsonify({'message': msg, 'is_active': user.is_active}), 200

@api_bp.route('/admin/delivery_persons/<int:user_id>/delete', methods=['POST'])
@token_required
def admin_delete_delivery_person(current_user, user_id):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    success, msg = DeliveryService.delete_delivery_person(user_id)
    if not success:
        return jsonify({'message': msg}), 400
    return jsonify({'message': msg}), 200

@api_bp.route('/admin/delivery_persons/<int:user_id>/shift/update', methods=['POST'])
@token_required
def admin_update_delivery_shift(current_user, user_id):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    data = request.get_json(silent=True) or {}
    shift_start = data.get('shift_start_time')
    shift_end = data.get('shift_end_time')
    max_orders = data.get('max_active_orders')
    success, msg = DeliveryService.update_shift(user_id, shift_start, shift_end, max_orders)
    if not success:
        return jsonify({'message': msg}), 400
    return jsonify({'message': msg}), 200

@api_bp.route('/admin/finance', methods=['GET'])
@token_required
def admin_finance(current_user):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    subscription_revenue = db.session.query(func.sum(Subscription.amount)).filter(Subscription.status == 'paid').scalar() or 0
    order_revenue = db.session.query(func.sum(Order.total)).filter(Order.status != 'cancelled').scalar() or 0
    delivery_fee_revenue = db.session.query(func.sum(Order.delivery_fee)).filter(Order.status != 'cancelled').scalar() or 0
    total_users = User.query.count()
    order_status_counts = {}
    for status in ['new', 'confirmed', 'preparing', 'ready', 'delivering', 'delivered', 'cancelled']:
        order_status_counts[status] = Order.query.filter_by(status=status).count()
    user_role_counts = {}
    for role in ['admin', 'owner', 'customer', 'delivery']:
        user_role_counts[role] = User.query.filter_by(role=role).count()
    return jsonify({
        'subscription_revenue': subscription_revenue,
        'order_revenue': order_revenue,
        'delivery_fee_revenue': delivery_fee_revenue,
        'total_users': total_users,
        'order_status_counts': order_status_counts,
        'user_role_counts': user_role_counts
    }), 200

@api_bp.route('/admin/chats', methods=['GET'])
@token_required
def admin_chat_users(current_user):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    users = User.query.filter(User.id != current_user.id).all()
    return jsonify({'users': [serialize_user(u) for u in users]}), 200

@api_bp.route('/admin/chats/<int:user_id>', methods=['GET'])
@token_required
def admin_chat_messages(current_user, user_id):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    messages = ChatMessage.query.filter(
        ((ChatMessage.sender_id == current_user.id) & (ChatMessage.receiver_id == user_id)) |
        ((ChatMessage.sender_id == user_id) & (ChatMessage.receiver_id == current_user.id))
    ).order_by(ChatMessage.created_at.asc()).all()
    messages_data = []
    for msg in messages:
        messages_data.append({
            'id': msg.id,
            'sender_id': msg.sender_id,
            'receiver_id': msg.receiver_id,
            'message': msg.message,
            'is_read': msg.is_read,
            'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M') if msg.created_at else None
        })
    return jsonify({'messages': messages_data}), 200

@api_bp.route('/admin/chats/send', methods=['POST'])
@token_required
def admin_send_message(current_user):
    if not is_admin(current_user):
        return jsonify({'message': 'غير مسموح'}), 403
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    message = data.get('message', '').strip()
    if not user_id or not message:
        return jsonify({'message': 'بيانات غير كاملة'}), 400
    msg = ChatMessage(
        sender_id=current_user.id,
        receiver_id=int(user_id),
        message=message,
        is_read=False
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify({'message': 'تم إرسال الرسالة'}), 201
