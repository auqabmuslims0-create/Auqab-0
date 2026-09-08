from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort, jsonify
from sqlalchemy.orm import joinedload
from database import db
from models import User, Product, Store, Favorite, Review
from shared.utils import safe_redirect_target, safe_referrer
from shared.decorators import login_required

account_bp = Blueprint('account', __name__)

def _is_ajax():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json

@account_bp.route('/favorite/toggle', methods=['POST'])
@login_required
def toggle_favorite_general():
    """تبديل المفضلة (منتج أو متجر) عبر JSON أو form."""
    user_id = session['user_id']
    data = request.get_json(silent=True) or {}
    fav_type = data.get('type') or request.form.get('type')
    fav_id = data.get('id') or request.form.get('id', type=int)

    if fav_type not in ['product', 'store'] or not fav_id:
        return jsonify({'status': 'error', 'message': 'بيانات غير صالحة'}), 400

    try:
        if fav_type == 'product':
            product = Product.query.get_or_404(fav_id)
            existing = Favorite.query.filter_by(user_id=user_id, product_id=product.id).first()
            if existing:
                db.session.delete(existing)
                db.session.commit()
                return jsonify({'status': 'success', 'message': 'تمت إزالة المنتج من المفضلة', 'is_favorite': False})
            else:
                fav = Favorite(user_id=user_id, product_id=product.id)
                db.session.add(fav)
                db.session.commit()
                return jsonify({'status': 'success', 'message': 'تمت إضافة المنتج إلى المفضلة', 'is_favorite': True})
        else:  # store
            store = Store.query.get_or_404(fav_id)
            existing = Favorite.query.filter_by(user_id=user_id, store_id=store.id).first()
            if existing:
                db.session.delete(existing)
                db.session.commit()
                return jsonify({'status': 'success', 'message': 'تمت إزالة المتجر من المفضلة', 'is_favorite': False})
            else:
                fav = Favorite(user_id=user_id, store_id=store.id)
                db.session.add(fav)
                db.session.commit()
                return jsonify({'status': 'success', 'message': 'تمت إضافة المتجر إلى المفضلة', 'is_favorite': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'حدث خطأ: {str(e)}'}), 500

@account_bp.route('/api/favorites/sync', methods=['POST'])
@login_required
def sync_favorites():
    data = request.get_json(silent=True) or {}
    favs = data.get('favorites', {})
    user_id = session['user_id']
    products = favs.get('products', [])
    stores = favs.get('stores', [])

    Favorite.query.filter_by(user_id=user_id).delete()
    for pid in products:
        try:
            pid_int = int(pid)
            if Product.query.get(pid_int):
                db.session.add(Favorite(user_id=user_id, product_id=pid_int))
        except (ValueError, TypeError):
            continue
    for sid in stores:
        try:
            sid_int = int(sid)
            if Store.query.get(sid_int):
                db.session.add(Favorite(user_id=user_id, store_id=sid_int))
        except (ValueError, TypeError):
            continue
    db.session.commit()
    return jsonify({'status': 'success'})

@account_bp.route('/favorites')
@login_required
def favorites():
    user_id = session['user_id']
    favs = Favorite.query.filter_by(user_id=user_id).options(
        joinedload(Favorite.product),
        joinedload(Favorite.store)
    ).all()
    return render_template('customer/favorites.html', favs=favs)

@account_bp.route('/favorite/toggle/product/<int:product_id>', methods=['POST'])
@login_required
def toggle_favorite_product(product_id):
    user_id = session['user_id']

    existing = Favorite.query.filter_by(user_id=user_id, product_id=product_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        message = 'تمت إزالة المنتج من المفضلة'
        is_favorite = False
    else:
        fav = Favorite(user_id=user_id, product_id=product_id)
        db.session.add(fav)
        db.session.commit()
        message = 'تمت إضافة المنتج إلى المفضلة'
        is_favorite = True

    if _is_ajax():
        return jsonify({'status': 'success', 'message': message, 'is_favorite': is_favorite})
    flash(message, 'success')
    next_url = safe_redirect_target(request.form.get('next')) or safe_referrer() or url_for('market.market')
    return redirect(next_url)

@account_bp.route('/favorite/toggle/store/<int:store_id>', methods=['POST'])
@login_required
def toggle_favorite_store(store_id):
    user_id = session['user_id']

    existing = Favorite.query.filter_by(user_id=user_id, store_id=store_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        message = 'تمت إزالة المتجر من المفضلة'
        is_favorite = False
    else:
        fav = Favorite(user_id=user_id, store_id=store_id)
        db.session.add(fav)
        db.session.commit()
        message = 'تمت إضافة المتجر إلى المفضلة'
        is_favorite = True

    if _is_ajax():
        return jsonify({'status': 'success', 'message': message, 'is_favorite': is_favorite})
    flash(message, 'success')
    next_url = safe_redirect_target(request.form.get('next')) or safe_referrer() or url_for('stores.stores_page')
    return redirect(next_url)

@account_bp.route('/product/<int:product_id>/review', methods=['POST'])
@login_required
def add_review(product_id):
    user_id = session['user_id']
    product = Product.query.get_or_404(product_id)

    rating_str = request.form.get('rating', '').strip()
    comment = request.form.get('comment', '').strip()

    try:
        rating = int(rating_str)
    except (TypeError, ValueError):
        rating = 0

    if rating < 1 or rating > 5:
        flash('التقييم يجب أن يكون بين 1 و 5', 'error')
        return redirect(url_for('stores.product_public', product_id=product.id))

    if not comment:
        flash('يرجى كتابة تعليق', 'error')
        return redirect(url_for('stores.product_public', product_id=product.id))

    existing = Review.query.filter_by(user_id=user_id, product_id=product.id).first()
    if existing:
        existing.rating = rating
        existing.comment = comment
    else:
        review = Review(
            user_id=user_id,
            product_id=product.id,
            rating=rating,
            comment=comment
        )
        db.session.add(review)

    db.session.commit()
    flash('تم حفظ تقييمك', 'success')
    return redirect(url_for('stores.product_public', product_id=product.id))
