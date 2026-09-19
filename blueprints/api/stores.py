from collections import deque
from datetime import datetime, timedelta
from threading import Lock

from flask import request, jsonify, abort
from database import db
from models import Store, Category, Product, Subscription
from shared.utils import save_image, save_video
from . import api_bp
from .helpers import token_required, serialize_store, serialize_product, get_image_url


DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


# ═══════════════════════════════════════════════════════════════
# A6: Rate limit بسيط لرفع الملفات (20/ساعة لكل IP)
# ═══════════════════════════════════════════════════════════════
# الحماية العامة في app.py تسمح بـ 100 طلب/ساعة لكل IP. هذا حد إضافي على
# مسارات الرفع تحديدًا — دفاع ضد إغراق Cloudinary أو القرص المحلي.
# in-memory: يعمل بشكل صحيح مع gunicorn --workers 1.
_UPLOAD_WINDOW_SECONDS = 3600
_UPLOAD_MAX_PER_IP = 20
_upload_attempts = {}
_upload_lock = Lock()


def _check_upload_rate_limit():
    """
    يعيد True إذا كان IP مسموحًا له بالرفع ويسجّل المحاولة.
    يعيد False إذا تجاوز الحد (20/ساعة).
    """
    ip = (request.remote_addr or 'unknown').strip()
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=_UPLOAD_WINDOW_SECONDS)
    with _upload_lock:
        bucket = _upload_attempts.get(ip)
        if bucket is None:
            bucket = deque()
            _upload_attempts[ip] = bucket
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= _UPLOAD_MAX_PER_IP:
            return False
        bucket.append(now)
        return True


def _paginate_args():
    """قراءة page/per_page بأمان (per_page محدود بين 1 و MAX_PER_PAGE)."""
    page = request.args.get('page', 1, type=int) or 1
    if page < 1:
        page = 1
    per_page = request.args.get('per_page', DEFAULT_PER_PAGE, type=int) or DEFAULT_PER_PAGE
    if per_page < 1:
        per_page = DEFAULT_PER_PAGE
    if per_page > MAX_PER_PAGE:
        per_page = MAX_PER_PAGE
    return page, per_page


def _pagination_meta(pagination):
    return {
        'page': pagination.page,
        'per_page': pagination.per_page,
        'total': pagination.total,
        'pages': pagination.pages,
        'has_next': pagination.has_next,
        'has_prev': pagination.has_prev,
    }


@api_bp.route('/stores', methods=['GET'])
def get_stores():
    page, per_page = _paginate_args()
    pagination = (
        Store.query
        .filter(Store.subscription_status == 'active')
        .order_by(Store.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    return jsonify({
        'stores': [serialize_store(s) for s in pagination.items],
        'pagination': _pagination_meta(pagination),
    }), 200


@api_bp.route('/stores/<int:store_id>', methods=['GET'])
def get_store(store_id):
    store = db.get_or_404(Store, store_id)
    if store.subscription_status != 'active':
        abort(404)
    return jsonify({'store': serialize_store(store)}), 200


@api_bp.route('/stores/<int:store_id>/categories', methods=['GET'])
def get_store_categories(store_id):
    store = db.get_or_404(Store, store_id)
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
    store = db.get_or_404(Store, store_id)
    if store.subscription_status != 'active':
        abort(404)

    category_id = request.args.get('category_id', type=int)
    page, per_page = _paginate_args()

    query = Product.query.filter_by(store_id=store.id)
    if category_id:
        query = query.filter_by(category_id=category_id)

    pagination = (
        query
        .order_by(Product.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    return jsonify({
        'products': [serialize_product(p) for p in pagination.items],
        'pagination': _pagination_meta(pagination),
    }), 200


@api_bp.route('/stores/mine', methods=['GET'])
@token_required
def get_my_stores(current_user):
    stores = Store.query.filter_by(owner_id=current_user.id).all()
    return jsonify({'stores': [serialize_store(s) for s in stores]}), 200


@api_bp.route('/stores/<int:store_id>/upload-images', methods=['POST'])
@token_required
def upload_product_images(current_user, store_id):
    if not _check_upload_rate_limit():
        return jsonify({'message': 'تم تجاوز حد الرفع المسموح، حاول بعد ساعة'}), 429
    store = db.get_or_404(Store, store_id)
    if store.owner_id != current_user.id and current_user.role != 'admin':
        return jsonify({'message': 'غير مسموح'}), 403
    files = request.files.getlist('files')
    if not files:
        return jsonify({'message': 'لم يتم إرسال ملفات'}), 400
    urls = []
    for file in files:
        if file and file.filename:
            try:
                saved_name = save_image(file)
            except ValueError as e:
                return jsonify({'message': str(e)}), 400
            if saved_name:
                urls.append(get_image_url(saved_name))
    return jsonify({'urls': urls}), 200


@api_bp.route('/stores/<int:store_id>/upload-video', methods=['POST'])
@token_required
def upload_product_video(current_user, store_id):
    if not _check_upload_rate_limit():
        return jsonify({'message': 'تم تجاوز حد الرفع المسموح، حاول بعد ساعة'}), 429
    store = db.get_or_404(Store, store_id)
    if store.owner_id != current_user.id and current_user.role != 'admin':
        return jsonify({'message': 'غير مسموح'}), 403
    file = request.files.get('files')
    if not file:
        return jsonify({'message': 'لم يتم إرسال ملف'}), 400
    try:
        saved_name = save_video(file)
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    if saved_name:
        return jsonify({'url': get_image_url(saved_name)}), 200
    return jsonify({'message': 'فشل رفع الملف'}), 500


@api_bp.route('/stores/<int:store_id>/upload-logo', methods=['POST'])
@token_required
def upload_store_logo(current_user, store_id):
    if not _check_upload_rate_limit():
        return jsonify({'message': 'تم تجاوز حد الرفع المسموح، حاول بعد ساعة'}), 429
    store = db.get_or_404(Store, store_id)
    if store.owner_id != current_user.id and current_user.role != 'admin':
        return jsonify({'message': 'غير مسموح'}), 403
    file = request.files.get('files')
    if not file:
        return jsonify({'message': 'لم يتم إرسال ملف'}), 400
    try:
        saved_name = save_image(file)
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    if saved_name:
        return jsonify({'url': get_image_url(saved_name)}), 200
    return jsonify({'message': 'فشل رفع الملف'}), 500


@api_bp.route('/stores/<int:store_id>/upload-proof', methods=['POST'])
@token_required
def upload_subscription_proof(current_user, store_id):
    if not _check_upload_rate_limit():
        return jsonify({'message': 'تم تجاوز حد الرفع المسموح، حاول بعد ساعة'}), 429
    store = db.get_or_404(Store, store_id)
    if store.owner_id != current_user.id and current_user.role != 'admin':
        return jsonify({'message': 'غير مسموح'}), 403
    file = request.files.get('files')
    if not file:
        return jsonify({'message': 'لم يتم إرسال ملف'}), 400
    try:
        saved_name = save_image(file)
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    if saved_name:
        return jsonify({'url': get_image_url(saved_name)}), 200
    return jsonify({'message': 'فشل رفع الملف'}), 500


@api_bp.route('/stores/<int:store_id>/subscription', methods=['GET'])
@token_required
def get_store_subscription(current_user, store_id):
    store = db.get_or_404(Store, store_id)
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
        'proof_image': get_image_url(sub.proof_image) if sub.proof_image else None,
        'start_date': sub.start_date.strftime('%Y-%m-%d') if sub.start_date else None,
        'end_date': sub.end_date.strftime('%Y-%m-%d') if sub.end_date else None
    }
    return jsonify({'subscription': sub_data}), 200
