from flask import request, jsonify, session
from database import db
from models import Favorite, User, Product, Store
from . import api_bp
from .helpers import token_required

@api_bp.route('/cart/sync', methods=['POST'])
@token_required
def sync_cart(current_user):
    """مزامنة السلة المحلية مع الجلسة على الخادم"""
    data = request.get_json(silent=True) or {}
    cart = data.get('cart')
    if cart is None:
        return jsonify({'message': 'يجب إرسال بيانات السلة'}), 400

    if not isinstance(cart, dict):
        return jsonify({'message': 'صيغة السلة غير صالحة'}), 400

    try:
        cleaned_cart = {}
        for key, qty in cart.items():
            try:
                product_id = int(key)
            except (ValueError, TypeError):
                continue
            try:
                quantity = int(qty)
            except (ValueError, TypeError):
                continue
            if quantity > 0:
                cleaned_cart[product_id] = quantity

        session['cart'] = cleaned_cart
        session.modified = True
        return jsonify({'message': 'تمت مزامنة السلة بنجاح', 'cart': cleaned_cart}), 200
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'حدث خطأ أثناء مزامنة السلة'}), 500

@api_bp.route('/favorites/sync', methods=['POST'])
@token_required
def sync_favorites(current_user):
    """مزامنة المفضلة المحلية مع قاعدة البيانات"""
    data = request.get_json(silent=True) or {}
    favorites_data = data.get('favorites')
    if favorites_data is None:
        return jsonify({'message': 'يجب إرسال بيانات المفضلة'}), 400

    if not isinstance(favorites_data, dict) or 'products' not in favorites_data or 'stores' not in favorites_data:
        return jsonify({'message': 'صيغة المفضلة غير صالحة'}), 400

    try:
        existing_favs = Favorite.query.filter_by(user_id=current_user.id).all()
        existing_products = set(fav.product_id for fav in existing_favs if fav.product_id)
        existing_stores = set(fav.store_id for fav in existing_favs if fav.store_id)

        new_products = set(int(pid) for pid in favorites_data.get('products', []) if str(pid).isdigit())
        new_stores = set(int(sid) for sid in favorites_data.get('stores', []) if str(sid).isdigit())

        for fav in existing_favs:
            if fav.product_id and fav.product_id not in new_products:
                db.session.delete(fav)
            elif fav.store_id and fav.store_id not in new_stores:
                db.session.delete(fav)

        for pid in new_products:
            if pid not in existing_products:
                product = Product.query.get(pid)
                if product:
                    db.session.add(Favorite(user_id=current_user.id, product_id=pid))

        for sid in new_stores:
            if sid not in existing_stores:
                store = Store.query.get(sid)
                if store:
                    db.session.add(Favorite(user_id=current_user.id, store_id=sid))

        db.session.commit()
        return jsonify({'message': 'تمت مزامنة المفضلة بنجاح'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'حدث خطأ أثناء مزامنة المفضلة: {str(e)}'}), 500

@api_bp.route('/profile/sync', methods=['POST'])
@token_required
def sync_profile(current_user):
    """مزامنة بيانات الملف الشخصي المحلية مع قاعدة البيانات"""
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'message': 'يجب إرسال بيانات الملف الشخصي'}), 400

    allowed_fields = ['username', 'email', 'phone', 'bio', 'dark_mode']
    updates = {}

    for field in allowed_fields:
        if field in data and data[field] is not None:
            updates[field] = data[field]

    if not updates:
        return jsonify({'message': 'لا توجد حقول للتحديث'}), 400

    try:
        if 'username' in updates:
            existing = User.query.filter(
                User.username == updates['username'],
                User.id != current_user.id
            ).first()
            if existing:
                return jsonify({'message': 'اسم المستخدم مستخدم بالفعل'}), 409

        if 'email' in updates:
            existing = User.query.filter(
                User.email == updates['email'],
                User.id != current_user.id
            ).first()
            if existing:
                return jsonify({'message': 'البريد الإلكتروني مستخدم بالفعل'}), 409

        for field, value in updates.items():
            setattr(current_user, field, value)

        db.session.commit()
        return jsonify({'message': 'تم تحديث الملف الشخصي بنجاح'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'حدث خطأ أثناء تحديث الملف الشخصي: {str(e)}'}), 500
