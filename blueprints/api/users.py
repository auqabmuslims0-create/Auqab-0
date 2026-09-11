from flask import request, jsonify
from database import db
from models import Favorite, Product, Store
from shared.utils import save_image
from . import api_bp
from .helpers import token_required, serialize_product, serialize_store

# ملاحظة (v1):
# تمت إزالة المسارات /notifications و /notifications/<id>/read من هذا الملف
# لأنها كانت تتعارض مع مسارات notifications_bp (نفس الـ URL: /api/notifications)
# والنسخة الموجودة في notifications_bp هي الأحدث وتستخدم الجلسة (session) لا JWT.


@api_bp.route('/favorites', methods=['GET'])
@token_required
def get_favorites(current_user):
    favs = Favorite.query.filter_by(user_id=current_user.id).all()
    favorites_data = []
    for fav in favs:
        item = {
            'id': fav.id,
            'product_id': fav.product_id,
            'store_id': fav.store_id,
            'created_at': fav.created_at.strftime('%Y-%m-%d %H:%M') if fav.created_at else None
        }
        if fav.product:
            item['product'] = serialize_product(fav.product)
        if fav.store:
            item['store'] = serialize_store(fav.store)
        favorites_data.append(item)
    return jsonify({'favorites': favorites_data}), 200


@api_bp.route('/favorites/toggle', methods=['POST'])
@token_required
def toggle_favorite(current_user):
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'message': 'يجب إرسال البيانات بصيغة JSON'}), 400

    fav_type = data.get('type')
    fav_id = data.get('id')

    if fav_type not in ['product', 'store'] or not fav_id:
        return jsonify({'message': 'نوع المفضلة غير صالح'}), 400

    try:
        if fav_type == 'product':
            product = Product.query.get_or_404(fav_id)
            existing = Favorite.query.filter_by(
                user_id=current_user.id, product_id=product.id
            ).first()
            if existing:
                db.session.delete(existing)
                db.session.commit()
                return jsonify({'message': 'تمت إزالة المنتج من المفضلة', 'is_favorite': False}), 200
            else:
                fav = Favorite(user_id=current_user.id, product_id=product.id)
                db.session.add(fav)
                db.session.commit()
                return jsonify({'message': 'تمت إضافة المنتج إلى المفضلة', 'is_favorite': True}), 200
        else:
            store = Store.query.get_or_404(fav_id)
            existing = Favorite.query.filter_by(
                user_id=current_user.id, store_id=store.id
            ).first()
            if existing:
                db.session.delete(existing)
                db.session.commit()
                return jsonify({'message': 'تمت إزالة المتجر من المفضلة', 'is_favorite': False}), 200
            else:
                fav = Favorite(user_id=current_user.id, store_id=store.id)
                db.session.add(fav)
                db.session.commit()
                return jsonify({'message': 'تمت إضافة المتجر إلى المفضلة', 'is_favorite': True}), 200
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'حدث خطأ أثناء تحديث المفضلة'}), 500
