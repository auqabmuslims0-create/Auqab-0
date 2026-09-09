from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, make_response
from sqlalchemy.orm import joinedload, selectinload
from datetime import timedelta
from database import db
from models import User, Product, Store, Category, ProductReaction, UserActivity
from shared.utils import is_store_open
from shared.time_utils import current_time

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

def _get_active_shoppers_count():
    """حساب عدد المستخدمين النشطين خلال آخر 5 دقائق."""
    try:
        now = current_time()
        active_interval = timedelta(minutes=5)
        count = db.session.query(UserActivity.user_id) \
            .join(User, User.id == UserActivity.user_id) \
            .filter(
                UserActivity.last_seen >= now - active_interval,
                User.role == 'customer',
                User.is_active == True
            ) \
            .distinct().count()
        return count
    except Exception:
        return 0

@market_bp.route('/api/active-shoppers')
def active_shoppers():
    """API لإرجاع عدد المتسوقين النشطين بدون حماية تسجيل دخول."""
    count = _get_active_shoppers_count()
    response = make_response(jsonify({
        'active_shoppers_count': count,
        'timestamp': current_time().strftime('%Y-%m-%d %H:%M:%S')
    }))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

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

    active_shoppers_count = _get_active_shoppers_count()

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
                           q=q,
                           active_shoppers_count=active_shoppers_count)
