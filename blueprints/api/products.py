from flask import request, jsonify, abort
from sqlalchemy.orm import selectinload
from models import Product, Store
from . import api_bp
from .helpers import serialize_product, token_required

@api_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.store and product.store.subscription_status != 'active':
        abort(404)
    return jsonify({'product': serialize_product(product, include_store=True)}), 200

@api_bp.route('/search', methods=['GET'])
def search():
    query = request.args.get('q', '').strip()
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)

    results_query = Product.query.join(Store).filter(Store.subscription_status == 'active')
    if query:
        results_query = results_query.filter(Product.name.ilike(f'%{query}%'))
    if min_price is not None:
        results_query = results_query.filter(Product.price >= min_price)
    if max_price is not None:
        results_query = results_query.filter(Product.price <= max_price)

    products = results_query.all()
    return jsonify({'products': [serialize_product(p) for p in products]}), 200

@api_bp.route('/products/<int:product_id>/reviews', methods=['GET'])
def get_product_reviews(product_id):
    product = Product.query.get_or_404(product_id)
    reviews = []
    for r in product.reviews:
        reviews.append({
            'id': r.id,
            'username': r.user.username if r.user else 'مستخدم',
            'rating': r.rating,
            'comment': r.comment,
            'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else None
        })
    return jsonify({'reviews': reviews}), 200
