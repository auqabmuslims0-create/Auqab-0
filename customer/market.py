from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from sqlalchemy.orm import joinedload, selectinload
from database import db
from models import User, Product, Store, Category, ProductReaction
from shared.utils import is_store_open

market_bp = Blueprint('market', __name__)

@market_bp.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))
    if user.role == 'admin':
        return redirect(url_for('admin.admin_dashboard'))
    elif user.role == 'owner':
        return redirect(url_for('store.my_stores'))
    elif user.role == 'delivery':
        return redirect(url_for('delivery.delivery_dashboard'))
    else:
        return redirect(url_for('market.market'))

@market_bp.route('/market')
def market():
    page = request.args.get('page', 1, type=int)
    per_page = 12
    category_id = request.args.get('category_id', type=int)
    store_id = request.args.get('store_id', type=int)
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    q = request.args.get('q', '').strip()

    query = Product.query.join(Store).filter(
        Store.subscription_status == 'active'
    )
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if store_id:
        query = query.filter(Product.store_id == store_id)
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)
    if q:
        query = query.filter(Product.name.ilike(f'%{q}%'))

    products_pagination = query \
        .options(
            selectinload(Product.store),
            selectinload(Product.category)
        ) \
        .order_by(Product.created_at.desc()) \
        .paginate(page=page, per_page=per_page, error_out=False)

    stores = Store.query.filter(Store.subscription_status == 'active').limit(50).all()
    open_stores = [s for s in stores if is_store_open(s)]

    categories = Category.query.join(Product).join(Store).filter(
        Store.subscription_status == 'active'
    ).distinct().all()

    cart = session.get('cart', {})
    cart_product_ids = set(cart.keys())

    user_reaction_map = {}
    if 'user_id' in session:
        user_reactions = ProductReaction.query.filter_by(user_id=session['user_id']).all()
        for r in user_reactions:
            user_reaction_map[r.product_id] = r.reaction_type

    return render_template('customer/market.html',
                           open_stores=open_stores,
                           products=products_pagination.items,
                           pagination=products_pagination,
                           cart_product_ids=cart_product_ids,
                           user_reaction_map=user_reaction_map,
                           categories=categories,
                           selected_category=category_id,
                           selected_store=store_id,
                           min_price=min_price,
                           max_price=max_price,
                           q=q)

@market_bp.route('/search')
def search():
    query = request.args.get('q', '').strip()
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    category_id = request.args.get('category_id', type=int)
    store_id = request.args.get('store_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = 12

    results_query = Product.query.join(Store).filter(
        Store.subscription_status == 'active'
    ).options(
        selectinload(Product.store),
        selectinload(Product.category)
    )

    if query:
        results_query = results_query.filter(
            (Product.name.ilike(f'%{query}%')) |
            (Product.description.ilike(f'%{query}%'))
        )
    if min_price is not None:
        results_query = results_query.filter(Product.price >= min_price)
    if max_price is not None:
        results_query = results_query.filter(Product.price <= max_price)
    if category_id:
        results_query = results_query.filter(Product.category_id == category_id)
    if store_id:
        results_query = results_query.filter(Product.store_id == store_id)

    pagination = results_query.order_by(Product.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    categories = Category.query.join(Product).join(Store).filter(
        Store.subscription_status == 'active'
    ).distinct().all()

    stores = Store.query.filter(Store.subscription_status == 'active').limit(20).all()

    return render_template('customer/search.html',
                           query=query,
                           results=pagination.items,
                           pagination=pagination,
                           min_price=min_price,
                           max_price=max_price,
                           selected_category=category_id,
                           selected_store=store_id,
                           categories=categories,
                           stores=stores)

@market_bp.route('/search_suggestions')
def search_suggestions():
    q = request.args.get('q', '').strip()
    limit = 5

    if q:
        stores = Store.query.filter(
            Store.subscription_status == 'active',
            Store.name.ilike(f'%{q}%')
        ).limit(limit).all()

        products = Product.query.join(Store).filter(
            Store.subscription_status == 'active',
            Product.name.ilike(f'%{q}%')
        ).options(selectinload(Product.store)).order_by(Product.created_at.desc()).limit(limit).all()
    else:
        stores = Store.query.filter(Store.subscription_status == 'active').limit(limit).all()
        products = Product.query.join(Store).filter(
            Store.subscription_status == 'active'
        ).options(selectinload(Product.store)).order_by(Product.created_at.desc()).limit(limit).all()

    services = [
        {'name': 'توصيل سريع', 'icon': 'bi-truck'},
        {'name': 'دفع عند الاستلام', 'icon': 'bi-cash-coin'},
        {'name': 'دعم فني', 'icon': 'bi-headset'}
    ]

    def get_image_url(filename):
        if not filename:
            return ''
        if filename.startswith('http'):
            return filename
        if filename.startswith('uploads/'):
            return url_for('static', filename=filename)
        return url_for('static', filename='uploads/' + filename)

    stores_data = []
    for s in stores:
        stores_data.append({'id': s.id, 'name': s.name, 'logo_url': get_image_url(s.logo_url)})

    products_data = []
    for p in products:
        first_image = ''
        if p.images:
            first_image = p.images.split(',')[0].strip()
        products_data.append({'id': p.id, 'name': p.name, 'price': p.price, 'image_url': get_image_url(first_image)})

    return jsonify({'stores': stores_data, 'products': products_data, 'services': services})
