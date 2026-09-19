"""
Customer cart routes.

ملاحظة تصميمية مهمة:
  كل مسار تحت /cart/* يتطلب تسجيل دخول — يضمنه before_request_checks
  في app.py (cart.* ليست في public_endpoints). لذا لا حاجة لفحص
  'user_id' in session داخل الـ views نفسها.

  الاستثناء الوحيد: /api/cart/sync — يبدأ بـ /api/ فيُعفى من الحماية
  (لأغراض مزامنة localStorage من التطبيقات المحمولة قبل تسجيل الدخول).
  بعد login، يُدمَج session['cart'] مع DB فورًا (انظر auth.login).
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, abort, g
from sqlalchemy.orm import joinedload, selectinload
from database import db
from models import Product, Store, Order, OrderItem
from shared.time_utils import current_time
from datetime import timedelta
from sqlalchemy import or_, and_
from shared.utils import safe_redirect_target, is_store_active
from shared.decorators import login_required
from shared.services.order_service import OrderService
from shared.services.cart_service import CartService

cart_bp = Blueprint('cart', __name__)


# سقف الطلبات المعروضة في صفحة السلة.
# في الإنتاج الفعلي، المستخدم نادرًا ما يكون لديه أكثر من 20-30 طلبًا خلال 24 ساعة.
# السقف يمنع انفجار الأداء إذا تراكمت طلبات (اختبارات الضغط، حسابات قديمة نشطة).
ORDERS_LIMIT = 50


# ═══════════════════════════════════════════════════════════════
# أدوات مساعدة (session + HTTP)
# ═══════════════════════════════════════════════════════════════
def _get_session_cart():
    return session.get('cart', {})


def _save_session_cart(cart):
    session['cart'] = cart
    session.modified = True


def _is_ajax():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json


def _load_active_stores():
    """B1: المتاجر النشطة ذات الإحداثيات — لعرض الخريطة في checkout."""
    return Store.query.filter(
        Store.subscription_status == 'active',
        Store.latitude.isnot(None),
        Store.longitude.isnot(None)
    ).all()


# ═══════════════════════════════════════════════════════════════
# عرض السلة
# ═══════════════════════════════════════════════════════════════
@cart_bp.route('/cart')
@login_required
def cart():
    user = g.user
    # دمج أي محتوى قديم في session مع DB (مثلاً من جهاز آخر أو ما قبل الـ merge)
    merged = CartService.merge_session_with_db(user.id, _get_session_cart())
    if db.session.dirty or db.session.new:
        db.session.commit()
    session['cart'] = merged

    grouped = {}
    if merged:
        product_ids = [int(pid) for pid in merged.keys()]
        products = Product.query.filter(Product.id.in_(product_ids)).options(
            joinedload(Product.store)
        ).all()
        product_map = {p.id: p for p in products}

        items = []
        for pid_str, qty in merged.items():
            pid = int(pid_str)
            if pid in product_map:
                items.append({'product': product_map[pid], 'quantity': qty})

        for item in items:
            store_id = item['product'].store_id
            if store_id not in grouped:
                grouped[store_id] = {'store': item['product'].store, 'cart_items': [], 'total': 0}
            effective_price = item['product'].effective_price
            grouped[store_id]['cart_items'].append(item)
            grouped[store_id]['total'] += effective_price * item['quantity']

    # الطلبات النشطة + المُسلَّمة خلال آخر 24 ساعة
    # ORDERS_LIMIT يمنع تحميل تاريخ طويل (في الإنتاج = سقف احتياطي، وفي الاختبارات
    # يمنع N+1 على قوائم ضخمة).
    cutoff = current_time() - timedelta(hours=24)
    orders = Order.query.filter(
        Order.customer_id == user.id,
        or_(
            Order.status != 'delivered',
            and_(
                Order.status == 'delivered',
                or_(
                    Order.delivered_at >= cutoff,
                    and_(Order.delivered_at.is_(None), Order.created_at >= cutoff)
                )
            )
        )
    ).options(
        selectinload(Order.store),
        selectinload(Order.items).selectinload(OrderItem.product),
        selectinload(Order.delivery_person)
    ).order_by(Order.created_at.desc()).limit(ORDERS_LIMIT).all()

    return render_template('customer/cart.html', grouped=grouped, orders=orders)


@cart_bp.route('/cart/count')
@login_required
def cart_count():
    merged = CartService.merge_session_with_db(g.user.id, _get_session_cart())
    if db.session.dirty or db.session.new:
        db.session.commit()
    session['cart'] = merged
    return jsonify({'cart_count': sum(merged.values())})


# ═══════════════════════════════════════════════════════════════
# مزامنة من localStorage (يُسمح للزوار أيضاً — لملء session)
# ═══════════════════════════════════════════════════════════════
@cart_bp.route('/api/cart/sync', methods=['POST'])
def sync_cart():
    """
    مزامنة سلة localStorage مع الخادم.
    - للمسجّلين: تُستبدل سلة DB بالكامل بمحتوى العميل.
    - للزوار: يُخزَّن في session، ثم يُدمَج مع DB عند login/register.
    """
    data = request.get_json(silent=True) or {}
    local_cart = data.get('cart', {})
    if not isinstance(local_cart, dict):
        return jsonify({'status': 'error', 'message': 'بيانات غير صالحة'}), 400

    if 'user_id' in session:
        user_id = session['user_id']
        new_cart = CartService.sync_from_client(user_id, local_cart)
        db.session.commit()
        session['cart'] = new_cart
    else:
        clean = CartService.sanitize_client_cart(local_cart)
        session['cart'] = {str(k): v for k, v in clean.items()}
    session.modified = True

    cart = _get_session_cart()
    return jsonify({'status': 'success', 'cart_count': sum(cart.values())})


# ═══════════════════════════════════════════════════════════════
# إضافة / تعديل / إزالة
# ═══════════════════════════════════════════════════════════════
@cart_bp.route('/cart/add/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    product = db.get_or_404(Product, product_id)
    quantity = request.form.get('quantity', 1, type=int) or 1
    if quantity < 1:
        quantity = 1

    cart = _get_session_cart()
    current_qty = cart.get(str(product_id), 0)
    is_ajax = _is_ajax()

    if current_qty + quantity > product.stock_quantity:
        if is_ajax:
            return jsonify({'status': 'error', 'message': 'المخزون غير كافٍ'}), 400
        flash('المخزون غير كافٍ', 'error')
        return redirect(request.referrer or url_for('market.market'))

    cart = CartService.add_to_db_cart(g.user.id, product, quantity)
    _save_session_cart(cart)

    if is_ajax:
        return jsonify({'status': 'success', 'message': 'تمت الإضافة إلى السلة', 'cart_count': sum(cart.values())})
    flash('تمت الإضافة إلى السلة')
    next_url = safe_redirect_target(request.form.get('next'))
    if next_url:
        return redirect(next_url)
    return redirect(request.referrer or url_for('market.market'))


@cart_bp.route('/cart/update/<int:product_id>', methods=['POST'])
@login_required
def update_cart(product_id):
    product = db.get_or_404(Product, product_id)
    action = request.form.get('action')
    cart = _get_session_cart()
    pid_str = str(product_id)
    is_ajax = _is_ajax()
    stock_error = False

    if action == 'remove':
        cart.pop(pid_str, None)
        CartService.remove_from_db_cart(g.user.id, product_id)
    else:
        new_qty = request.form.get('quantity', 1, type=int) or 1
        if new_qty < 1:
            cart.pop(pid_str, None)
            CartService.remove_from_db_cart(g.user.id, product_id)
        elif new_qty > product.stock_quantity:
            cart[pid_str] = product.stock_quantity
            stock_error = True
            CartService.set_quantity(g.user.id, product, product.stock_quantity)
        else:
            cart[pid_str] = new_qty
            CartService.set_quantity(g.user.id, product, new_qty)

    _save_session_cart(cart)

    if is_ajax:
        if stock_error:
            return jsonify({
                'status': 'error',
                'message': 'المخزون غير كافٍ',
                'cart_count': sum(cart.values())
            }), 400
        effective_price = product.effective_price
        item_total = effective_price * cart.get(pid_str, 0)
        return jsonify({
            'status': 'success',
            'cart_count': sum(cart.values()),
            'item_total': item_total,
            'quantity': cart.get(pid_str, 0)
        })

    if stock_error:
        flash('المخزون غير كافٍ', 'error')
    return redirect(request.referrer or url_for('cart.cart'))


@cart_bp.route('/cart/remove/<int:product_id>', methods=['POST'])
@login_required
def remove_from_cart(product_id):
    cart = _get_session_cart()
    pid_str = str(product_id)
    cart.pop(pid_str, None)
    _save_session_cart(cart)

    CartService.remove_from_db_cart(g.user.id, product_id)

    if _is_ajax():
        return jsonify({'status': 'success', 'message': 'تمت إزالة المنتج من السلة', 'cart_count': sum(cart.values())})
    flash('تمت إزالة المنتج من السلة', 'success')
    return redirect(request.referrer or url_for('cart.cart'))


@cart_bp.route('/cart/clear', methods=['POST'])
@login_required
def clear_cart():
    session.pop('cart', None)
    CartService.clear_user_cart(g.user.id)
    flash('تم مسح السلة بالكامل', 'success')
    return redirect(url_for('cart.cart'))


@cart_bp.route('/cart/clear/<int:store_id>', methods=['POST'])
@login_required
def clear_store_cart(store_id):
    cart = _get_session_cart()
    if not cart:
        return redirect(url_for('cart.cart'))

    CartService.clear_store_cart(g.user.id, store_id)

    product_ids = CartService.get_store_product_ids(store_id)
    for pid in product_ids:
        cart.pop(pid, None)

    _save_session_cart(cart)
    flash('تم مسح منتجات هذا المتجر من السلة', 'success')
    return redirect(url_for('cart.cart'))


# ═══════════════════════════════════════════════════════════════
# الدفع
# ═══════════════════════════════════════════════════════════════
@cart_bp.route('/cart/checkout/<int:store_id>', methods=['GET'])
@login_required
def checkout(store_id):
    user = g.user
    if not user.is_active:
        flash('الحساب محظور')
        return redirect(url_for('auth.login'))

    cart = _get_session_cart()
    if not cart:
        return redirect(url_for('cart.cart'))

    store = db.get_or_404(Store, store_id)

    if not is_store_active(store):
        flash('هذا المتجر غير نشط حالياً ولا يمكن الطلب منه')
        return redirect(url_for('cart.cart'))

    product_ids = [int(pid) for pid in cart.keys()]
    products = Product.query.filter(
        Product.id.in_(product_ids),
        Product.store_id == store.id
    ).options(joinedload(Product.store)).all()
    product_map = {p.id: p for p in products}

    items = []
    for pid_str, qty in cart.items():
        product = product_map.get(int(pid_str))
        if product:
            items.append({'product': product, 'quantity': qty})

    if not items:
        flash('لا توجد منتجات لهذا المتجر في السلة')
        return redirect(url_for('cart.cart'))

    totals = OrderService.compute_order_totals(store, items)
    all_stores = _load_active_stores()

    return render_template('customer/checkout.html',
                           store=store,
                           items=items,
                           total=totals['product_total'],
                           delivery_fee=totals['delivery_fee'],
                           grand_total=totals['grand_total'],
                           all_stores=all_stores)


@cart_bp.route('/cart/checkout/<int:store_id>', methods=['POST'])
@login_required
def place_order(store_id):
    user = g.user
    if not user.is_active:
        if request.is_json:
            return jsonify({'message': 'الحساب محظور'}), 403
        flash('الحساب محظور')
        return redirect(url_for('auth.login'))

    store = db.get_or_404(Store, store_id)

    if not is_store_active(store):
        if request.is_json:
            return jsonify({'message': 'هذا المتجر غير نشط حالياً ولا يمكن الطلب منه'}), 400
        flash('هذا المتجر غير نشط حالياً ولا يمكن الطلب منه')
        return redirect(url_for('cart.cart'))

    if request.is_json:
        data = request.get_json(silent=True) or {}
        delivery_address = data.get('delivery_address', '').strip()
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        items_data = data.get('items', [])
        if not items_data:
            return jsonify({'message': 'يجب توفير عناصر الطلب'}), 400
        cart_items = []
        for item in items_data:
            product_id = item.get('product_id')
            quantity = item.get('quantity', 1)
            options_selected = item.get('options_selected')
            product = db.session.get(Product, product_id)
            if product and product.store_id == store.id:
                cart_items.append({'product': product, 'quantity': quantity, 'options_selected': options_selected})
        if not cart_items:
            return jsonify({'message': 'لا توجد منتجات صالحة'}), 400
    else:
        cart = _get_session_cart()
        if not cart:
            return redirect(url_for('cart.cart'))

        product_ids = [int(pid) for pid in cart.keys()]
        products = Product.query.filter(
            Product.id.in_(product_ids),
            Product.store_id == store.id
        ).all()
        product_map = {p.id: p for p in products}

        cart_items = []
        for pid_str, qty in cart.items():
            product = product_map.get(int(pid_str))
            if product:
                cart_items.append({'product': product, 'quantity': qty, 'options_selected': None})

        if not cart_items:
            if request.is_json:
                return jsonify({'message': 'لا توجد منتجات لهذا المتجر في السلة'}), 400
            flash('لا توجد منتجات لهذا المتجر في السلة')
            return redirect(url_for('cart.cart'))

        delivery_address = None
        latitude = longitude = None
        if store.has_delivery:
            delivery_address = request.form.get('delivery_address', '').strip()
            if not delivery_address:
                if request.is_json:
                    return jsonify({'message': 'العنوان مطلوب لخدمة التوصيل'}), 400
                flash('العنوان مطلوب لخدمة التوصيل')
                return redirect(url_for('cart.checkout', store_id=store.id))
            latitude = request.form.get('latitude', type=float)
            longitude = request.form.get('longitude', type=float)
            if not latitude or not longitude:
                if request.is_json:
                    return jsonify({'message': 'يرجى تحديد موقع التوصيل على الخريطة'}), 400
                flash('يرجى تحديد موقع التوصيل على الخريطة')
                return redirect(url_for('cart.checkout', store_id=store.id))

    payment_method = 'cash'

    try:
        order = OrderService.create_order(
            user=user, store=store, cart_items=cart_items,
            delivery_address=delivery_address, latitude=latitude, longitude=longitude,
            payment_method=payment_method
        )
        if not request.is_json:
            cart = _get_session_cart()
            removed_ids = []
            for item in cart_items:
                cart.pop(str(item['product'].id), None)
                removed_ids.append(item['product'].id)
            CartService.remove_products_from_db_cart(user.id, removed_ids)
            db.session.commit()
            _save_session_cart(cart)
            flash('تم تقديم الطلب بنجاح')
            return redirect(url_for('cart.cart'))
        else:
            return jsonify({'message': 'تم تقديم الطلب بنجاح'}), 201
    except ValueError as e:
        db.session.rollback()
        if request.is_json:
            return jsonify({'message': str(e)}), 400
        flash(str(e), 'error')
        return redirect(url_for('cart.cart'))
    except Exception:
        db.session.rollback()
        if request.is_json:
            return jsonify({'message': 'حدث خطأ أثناء إنشاء الطلب، حاول مرة أخرى'}), 500
        flash('حدث خطأ أثناء إنشاء الطلب، حاول مرة أخرى', 'error')
        return redirect(url_for('cart.cart'))


@cart_bp.route('/cart/buy/<int:product_id>', methods=['GET'])
@login_required
def buy_product(product_id):
    user = g.user
    if not user.is_active:
        flash('الحساب محظور')
        return redirect(url_for('auth.login'))

    product = db.get_or_404(Product, product_id)
    store = product.store
    if not is_store_active(store):
        flash('هذا المتجر غير نشط حالياً ولا يمكن الطلب منه')
        return redirect(url_for('cart.cart'))

    quantity = request.args.get('quantity', 1, type=int)
    if quantity < 1:
        quantity = 1
    if quantity > product.stock_quantity:
        quantity = product.stock_quantity

    items = [{'product': product, 'quantity': quantity, 'options_selected': None}]
    totals = OrderService.compute_order_totals(store, items)
    all_stores = _load_active_stores()

    return render_template('customer/checkout.html',
                           store=store,
                           items=items,
                           total=totals['product_total'],
                           delivery_fee=totals['delivery_fee'],
                           grand_total=totals['grand_total'],
                           all_stores=all_stores)


# ═══════════════════════════════════════════════════════════════
# إدارة الطلبات
# ═══════════════════════════════════════════════════════════════
@cart_bp.route('/cart/order/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    user = g.user
    order = db.get_or_404(Order, order_id)

    try:
        OrderService.cancel_order(user, order)
        flash('تم إلغاء الطلب بنجاح', 'success')
    except PermissionError as e:
        flash(str(e), 'error')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception:
        db.session.rollback()
        flash('حدث خطأ أثناء إلغاء الطلب', 'error')

    return redirect(url_for('cart.cart'))


@cart_bp.route('/cart/order/<int:order_id>/delete', methods=['POST'])
@login_required
def delete_order(order_id):
    user = g.user
    order = db.get_or_404(Order, order_id)

    try:
        OrderService.delete_order(user, order)
        flash('تم حذف الطلب بنجاح', 'success')
    except PermissionError as e:
        flash(str(e), 'error')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception:
        db.session.rollback()
        flash('تعذر حذف الطلب، حاول مرة أخرى', 'error')

    return redirect(url_for('cart.cart'))
