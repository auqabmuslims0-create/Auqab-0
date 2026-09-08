from functools import wraps
from flask import request, jsonify, url_for, current_app
from datetime import timedelta
import jwt
from database import db
import models
from shared.utils import get_upload_path
from shared.time_utils import current_time

def encode_auth_token(user_id):
    """توليد JWT token."""
    payload = {
        'user_id': user_id,
        'exp': current_time() + timedelta(days=1)
    }
    return jwt.encode(payload, current_app.config['JWT_SECRET_KEY'], algorithm='HS256')

def decode_auth_token(token):
    """فك تشفير JWT token وإرجاع user_id."""
    try:
        payload = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
        return payload['user_id']
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def token_required(f):
    """ديكوريتور للتحقق من JWT token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'message': 'الرمز مفقود'}), 401
        user_id = decode_auth_token(token)
        if not user_id:
            return jsonify({'message': 'الرمز غير صالح أو منتهي'}), 401
        current_user = db.session.get(models.User, user_id)
        if not current_user:
            return jsonify({'message': 'المستخدم غير موجود'}), 401
        if not current_user.is_active:
            return jsonify({'message': 'الحساب محظور'}), 403
        return f(current_user, *args, **kwargs)
    return decorated

def get_image_url(filename):
    """تحويل اسم الملف إلى رابط كامل."""
    if not filename:
        return None
    if filename.startswith('http'):
        return filename
    if filename.startswith('uploads/'):
        return url_for('static', filename=filename, _external=True)
    return url_for('static', filename='uploads/' + filename, _external=True)

def serialize_user(user):
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'phone': user.phone,
        'role': user.role,
        'public_id': user.public_id,
        'is_active': user.is_active,
        'created_at': user.created_at.strftime('%Y-%m-%d %H:%M') if user.created_at else None,
        'avatar': get_image_url(user.avatar),
        'shift_start_time': user.shift_start_time.strftime('%H:%M') if user.shift_start_time else None,
        'shift_end_time': user.shift_end_time.strftime('%H:%M') if user.shift_end_time else None,
        'max_active_orders': user.max_active_orders
    }

def serialize_store(store):
    return {
        'id': store.id,
        'owner_id': store.owner_id,
        'name': store.name,
        'description': store.description,
        'logo_url': get_image_url(store.logo_url),
        'phone': store.phone,
        'address': store.address,
        'working_hours': store.working_hours,
        'has_delivery': store.has_delivery,
        'subscription_status': store.subscription_status,
        'subscription_expiry': store.subscription_expiry.strftime('%Y-%m-%d') if store.subscription_expiry else None,
        'latitude': store.latitude,
        'longitude': store.longitude,
        'created_at': store.created_at.strftime('%Y-%m-%d %H:%M') if store.created_at else None
    }

def serialize_product(product, include_store=False):
    data = {
        'id': product.id,
        'name': product.name,
        'product_code': product.product_code,
        'description': product.description,
        'price': product.price,
        'stock_quantity': product.stock_quantity,
        'options': product.options,
        'images': [get_image_url(img) for img in (product.images.split(',') if product.images else [])],
        'video': get_image_url(product.video),
        'created_at': product.created_at.strftime('%Y-%m-%d %H:%M') if product.created_at else None,
        'category_id': product.category_id,
        'store_id': product.store_id,
        'store_name': product.store.name if product.store else None
    }
    if include_store and product.store:
        data['store'] = serialize_store(product.store)
    return data

def serialize_order(order):
    items = []
    for item in order.items:
        items.append({
            'product_id': item.product_id,
            'product_name': item.product.name if item.product else 'منتج محذوف',
            'quantity': item.quantity,
            'price': item.price,
            'options_selected': item.options_selected
        })
    return {
        'id': order.id,
        'customer_id': order.customer_id,
        'store_id': order.store_id,
        'delivery_person_id': order.delivery_person_id,
        'store': serialize_store(order.store) if order.store else None,
        'status': order.status,
        'total': order.total,
        'delivery_fee': order.delivery_fee,
        'delivery_code': order.delivery_code,
        'delivery_address': order.delivery_address,
        'latitude': order.latitude,
        'longitude': order.longitude,
        'is_cancelled': order.is_cancelled,
        'created_at': order.created_at.strftime('%Y-%m-%d %H:%M') if order.created_at else None,
        'delivered_at': order.delivered_at.strftime('%Y-%m-%d %H:%M') if order.delivered_at else None,
        'items': items
    }

def serialize_notification(notif):
    return {
        'id': notif.id,
        'title': notif.title,
        'message': notif.message,
        'link': notif.link,
        'type': notif.type,
        'priority': notif.priority,
        'icon': notif.icon,
        'is_read': notif.is_read,
        'extra_data': notif.extra_data,
        'created_at': notif.created_at.strftime('%Y-%m-%d %H:%M') if notif.created_at else None,
        'read_at': notif.read_at.strftime('%Y-%m-%d %H:%M') if notif.read_at else None,
        'expires_at': notif.expires_at.strftime('%Y-%m-%d %H:%M') if notif.expires_at else None
    }

def is_admin(user):
    return user.role == 'admin'
