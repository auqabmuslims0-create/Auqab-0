from flask import request, jsonify, abort, url_for
from database import db
from models import Store, Category, Product, Subscription
from shared.utils import save_image, save_video
from . import api_bp
from .helpers import token_required, serialize_store, serialize_product

@api_bp.route('/stores', methods=['GET'])
def get_stores():
    stores = Store.query.filter(Store.subscription_status == 'active').all()
    return jsonify({'stores': [serialize_store(s) for s in stores]}), 200

@api_bp.route('/stores/<int:store_id>', methods=['GET'])
def get_store(store_id):
    store = Store.query.get_or_404(store_id)
    if store.subscription_status != 'active':
        abort(404)
    return jsonify({'store': serialize_store(store)}), 200

@api_bp.route('/stores/<int:store_id>/categories', methods=['GET'])
def get_store_categories(store_id):
    store = Store.query.get_or_404(store_id)
    if store.subscription_status != 'active':
        abort(404)
    categories = Category.query.filter_by(store_id=store.id).all()
    cats_data = []
    for cat in categories:
        cats_data.append({
            'id': cat.id,
            'name': cat.name,
            'parent_id': cat.parent_id,
            'store_id': cat.store_id
        })
    return jsonify({'categories': cats_data}), 200

@api_bp.route('/stores/<int:store_id>/products', methods=['GET'])
def get_store_products(store_id):
    store = Store.query.get_or_404(store_id)
    if store.subscription_status != 'active':
        abort(404)
    category_id = request.args.get('category_id', type=int)
    if category_id:
        products = Product.query.filter_by(store_id=store.id, category_id=category_id).all()
    else:
        products = Product.query.filter_by(store_id=store.id).all()
    return jsonify({'products': [serialize_product(p) for p in products]}), 200

@api_bp.route('/stores/mine', methods=['GET'])
@token_required
def get_my_stores(current_user):
    stores = Store.query.filter_by(owner_id=current_user.id).all()
    return jsonify({'stores': [serialize_store(s) for s in stores]}), 200

@api_bp.route('/stores/<int:store_id>/upload-images', methods=['POST'])
@token_required
def upload_product_images(current_user, store_id):
    store = Store.query.get_or_404(store_id)
    if store.owner_id != current_user.id and current_user.role != 'admin':
        return jsonify({'message': 'غير مسموح'}), 403
    files = request.files.getlist('files')
    if not files:
        return jsonify({'message': 'لم يتم إرسال ملفات'}), 400
    urls = []
    for file in files:
        if file and file.filename:
            saved_name = save_image(file)
            if saved_name:
                urls.append(url_for('static', filename='uploads/' + saved_name, _external=True))
    return jsonify({'urls': urls}), 200

@api_bp.route('/stores/<int:store_id>/upload-video', methods=['POST'])
@token_required
def upload_product_video(current_user, store_id):
    store = Store.query.get_or_404(store_id)
    if store.owner_id != current_user.id and current_user.role != 'admin':
        return jsonify({'message': 'غير مسموح'}), 403
    file = request.files.get('files')
    if not file:
        return jsonify({'message': 'لم يتم إرسال ملف'}), 400
    saved_name = save_video(file)
    if saved_name:
        return jsonify({'url': url_for('static', filename='uploads/' + saved_name, _external=True)}), 200
    return jsonify({'message': 'فشل رفع الملف'}), 500

@api_bp.route('/stores/<int:store_id>/upload-logo', methods=['POST'])
@token_required
def upload_store_logo(current_user, store_id):
    store = Store.query.get_or_404(store_id)
    if store.owner_id != current_user.id and current_user.role != 'admin':
        return jsonify({'message': 'غير مسموح'}), 403
    file = request.files.get('files')
    if not file:
        return jsonify({'message': 'لم يتم إرسال ملف'}), 400
    saved_name = save_image(file)
    if saved_name:
        return jsonify({'url': url_for('static', filename='uploads/' + saved_name, _external=True)}), 200
    return jsonify({'message': 'فشل رفع الملف'}), 500

@api_bp.route('/stores/<int:store_id>/upload-proof', methods=['POST'])
@token_required
def upload_subscription_proof(current_user, store_id):
    store = Store.query.get_or_404(store_id)
    if store.owner_id != current_user.id and current_user.role != 'admin':
        return jsonify({'message': 'غير مسموح'}), 403
    file = request.files.get('files')
    if not file:
        return jsonify({'message': 'لم يتم إرسال ملف'}), 400
    saved_name = save_image(file)
    if saved_name:
        return jsonify({'url': url_for('static', filename='uploads/' + saved_name, _external=True)}), 200
    return jsonify({'message': 'فشل رفع الملف'}), 500

@api_bp.route('/stores/<int:store_id>/subscription', methods=['GET'])
@token_required
def get_store_subscription(current_user, store_id):
    store = Store.query.get_or_404(store_id)
    if store.owner_id != current_user.id and current_user.role != 'admin':
        return jsonify({'message': 'غير مسموح'}), 403
    sub = Subscription.query.filter_by(store_id=store.id).order_by(Subscription.start_date.desc()).first()
    if not sub:
        return jsonify({'subscription': None}), 200
    sub_data = {
        'id': sub.id,
        'store_id': sub.store_id,
        'user_id': sub.user_id,
        'amount': sub.amount,
        'status': sub.status,
        'payment_ref': sub.payment_ref,
        'proof_image': url_for('static', filename='uploads/' + sub.proof_image, _external=True) if sub.proof_image else None,
        'start_date': sub.start_date.strftime('%Y-%m-%d') if sub.start_date else None,
        'end_date': sub.end_date.strftime('%Y-%m-%d') if sub.end_date else None
    }
    return jsonify({'subscription': sub_data}), 200
