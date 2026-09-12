from flask import Blueprint, render_template, request, jsonify, make_response
from sqlalchemy.orm import joinedload
from models import Product, Store, Category

offers_bp = Blueprint('offers', __name__)


def _wants_json():
    return (request.args.get('format') == 'json'
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest')


@offers_bp.route('/offers')
def offers_page():
    q = request.args.get('q', '').strip()
    category_id = request.args.get('category_id', type=int)
    store_id = request.args.get('store_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = 12

    query = Product.query.join(Store).filter(
        Product.is_offer == True,
        Store.subscription_status == 'active'
    ).options(
        joinedload(Product.store),
        joinedload(Product.category)
    ).order_by(Product.created_at.desc())

    if q:
        query = query.filter(Product.name.ilike(f'%{q}%'))
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if store_id:
        query = query.filter(Product.store_id == store_id)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # ===== استجابة AJAX =====
    if _wants_json():
        html = render_template('customer/_product_cards.html',
                               products=pagination.items,
                               user_reaction_map=None)
        resp = make_response(jsonify({
            'html': html,
            'has_next': pagination.has_next,
            'next_page': pagination.next_num if pagination.has_next else None,
            'total': pagination.total,
        }))
        resp.headers['Cache-Control'] = 'private, max-age=0, no-store'
        return resp
    # ========================

    categories = Category.query.join(Product).filter(
        Product.is_offer == True,
        Product.store.has(Store.subscription_status == 'active')
    ).distinct().all()

    stores = Store.query.join(Product).filter(
        Product.is_offer == True,
        Store.subscription_status == 'active'
    ).distinct().all()

    return render_template('customer/offers.html',
                           products=pagination.items,
                           pagination=pagination,
                           q=q,
                           selected_category=category_id,
                           selected_store=store_id,
                           categories=categories,
                           stores=stores)
