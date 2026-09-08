from flask import Blueprint, render_template, request, abort, session
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import or_
from database import db
from models import Store, User, Product, Category, Favorite, Review, ProductComment, ProductReaction
from shared.utils import is_store_open, is_store_active

stores_bp = Blueprint('stores', __name__)

@stores_bp.route('/stores')
def stores_page():
    q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 9

    query = Store.query.filter(Store.subscription_status == 'active').options(
        joinedload(Store.owner)
    )

    if q:
        query = query.join(User, Store.owner_id == User.id).filter(
            or_(
                Store.name.ilike(f'%{q}%'),
                User.username.ilike(f'%{q}%')
            )
        )

    if status_filter in ['open', 'closed']:
        all_stores = query.order_by(Store.name).limit(500).all()
        open_status = {s.id: is_store_open(s) for s in all_stores}
        if status_filter == 'open':
            filtered = [s for s in all_stores if open_status.get(s.id, False)]
        else:
            filtered = [s for s in all_stores if not open_status.get(s.id, False)]
        total = len(filtered)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        end = start + per_page
        stores_page_items = filtered[start:end]

        class PaginationStub:
            def __init__(self, items, page, total_pages, total):
                self.items = items
                self.page = page
                self.pages = total_pages
                self.total = total
                self.has_prev = page > 1
                self.has_next = page < total_pages
                self.prev_num = page - 1 if self.has_prev else None
                self.next_num = page + 1 if self.has_next else None
            def iter_pages(self, left_edge=2, left_current=2, right_current=3, right_edge=2):
                last = 0
                for num in range(1, self.pages + 1):
                    if num <= left_edge or (num > self.page - left_current - 1 and num < self.page + right_current) or num > self.pages - right_edge:
                        if last + 1 != num:
                            yield None
                        yield num
                        last = num
        pagination = PaginationStub(stores_page_items, page, total_pages, total)
        open_status_for_template = open_status
    else:
        pagination = query.order_by(Store.name).paginate(page=page, per_page=per_page, error_out=False)
        stores_page_items = pagination.items
        open_status_for_template = {s.id: is_store_open(s) for s in stores_page_items}

    return render_template('customer/stores.html',
                           stores=stores_page_items,
                           pagination=pagination,
                           open_status=open_status_for_template,
                           q=q,
                           status_filter=status_filter)

@stores_bp.route('/store/<int:store_id>/public')
def store_public(store_id):
    store = db.session.get(Store, store_id)
    if not store or not is_store_active(store):
        abort(404)

    categories = Category.query.filter_by(store_id=store.id).all()
    category_id = request.args.get('category_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = 12

    products_query = Product.query.filter_by(store_id=store.id).options(
        joinedload(Product.category)
    )
    if category_id:
        products_query = products_query.filter_by(category_id=category_id)

    products_pagination = products_query.order_by(Product.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    store_videos = Product.query.filter(
        Product.store_id == store.id,
        Product.video.isnot(None)
    ).options(joinedload(Product.store), joinedload(Product.category)).all()

    is_favorite = False
    if 'user_id' in session:
        existing_fav = Favorite.query.filter_by(user_id=session['user_id'], store_id=store.id).first()
        if existing_fav:
            is_favorite = True

    open_status = is_store_open(store)
    featured_products = Product.query.filter_by(store_id=store.id).order_by(Product.views.desc()).limit(5).all()

    return render_template(
        'customer/store_public.html',
        store=store,
        categories=categories,
        products=products_pagination.items,
        pagination=products_pagination,
        selected_category=category_id,
        is_favorite=is_favorite,
        open_status=open_status,
        store_videos=store_videos,
        featured_products=featured_products
    )

@stores_bp.route('/product/<int:product_id>')
def product_public(product_id):
    product = Product.query.options(
        joinedload(Product.store),
        joinedload(Product.category),
        selectinload(Product.reviews).selectinload(Review.user),
        selectinload(Product.comments).selectinload(ProductComment.user),
        selectinload(Product.reactions)
    ).filter_by(id=product_id).first_or_404()

    if not is_store_active(product.store):
        abort(404)

    reviews = product.reviews
    reviews_count = len(reviews) if reviews else 0
    if reviews_count > 0:
        avg_rating = round(sum(r.rating for r in reviews) / reviews_count, 1)
    else:
        avg_rating = 0

    is_favorite = False
    if 'user_id' in session:
        existing_fav = Favorite.query.filter_by(user_id=session['user_id'], product_id=product.id).first()
        if existing_fav:
            is_favorite = True

    try:
        product.views += 1
        db.session.commit()
    except Exception:
        db.session.rollback()

    return render_template(
        'customer/product_public.html',
        product=product,
        store=product.store,
        is_favorite=is_favorite,
        avg_rating=avg_rating,
        reviews_count=reviews_count
    )
