from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, abort
from sqlalchemy.orm import joinedload
from database import db
from models import Product, CartItem, Store, Order, OrderItem, OrderStatusHistory, Payment, User
from shared.time_utils import current_time
from datetime import timedelta
from shared.utils import safe_redirect_target, is_store_active, get_setting
from shared.decorators import login_required
from shared.services.order_service import OrderService

cart_bp = Blueprint('cart', __name__)

def _get_session_cart():
    return session.get('cart', {})

def _save_session_cart(cart):
    session['cart'] = cart
    session.modified = True

def _merge_cart_with_db(user_id, session_cart):
    """دمج سلة الجلسة مع سلة قاعدة البيانات، دون commit (يترك للمتصل)."""
    if not user_id:
        return session_cart

    db_items = CartItem.query.filter_by(user_id=user_id).all()
    db_cart = {str(item.product_id): item.quantity for item in db_items}

    for pid, qty in session_cart.items():
        if pid in db_cart:
            db_cart[pid] = max(db_cart[pid], qty)
        else:
            db_cart[pid] = qty

    for pid, qty in db_cart.items():
        product_id = int(pid)
        product = db.session.get(Product, product_id)
        if not product:
            continue
        existing = CartItem.query.filter_by(
            user_id=user_id, product_id=product_id
        ).first()
        if existing:
            existing.quantity = min(qty, product.stock_quantity)
        else:
            db.session.add(CartItem(
                user_id=user_id,
                product_id=product_id,
                store_id=product.store_id,
                quantity=min(qty, product.stock_quantity)
            ))

    updated_cart = {str(item.product_id): item.quantity for item in CartItem.query.filter_by(user_id=user_id).all()}
    session['cart'] = updated_cart
    return updated_cart

def _is_ajax():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json

@cart_bp.route('/cart')
def cart():
    if 'user_id' in session:
        user_id = session['user_id']
        session_cart = _get_session_cart()
        _merge_cart_with_db(user_id, session_cart)
        if db.session.dirty or db.session.new:
            db.session.commit()

    cart = _get_session_cart()
    grouped = {}

    if cart:
        product_ids = [int(pid) for pid in cart.keys()]
        products = Product.query.filter(Product.id.in_(product_ids)).options(
            joinedload(Product.store)
        ).all()
        product_map = {p.id: p for p in products}

        items = []
        for pid_str, qty in cart.items():
            pid = int(pid_str)
            if pid in product_map:
                items.append({'product': product_map[pid], 'quantity': qty})

        for item in items:
            store_id = item['product'].store_id
            if store_id not in grouped:
                grouped[store_id] = {'store': item['product'].store, 'cart_items': [], 'total': 0}
            effective_price = OrderService.get_effective_price(item['product'])
            grouped[store_id]['cart_items'].append(item)
            grouped[store_id]['total'] += effective_price * item['quantity']

    orders = []
    if 'user_id' in session:
        user = db.session.get(User, session['user_id'])
        if user:
            cutoff = current_time() - timedelta(hours=24)
            all_orders = Order.query.filter_by(customer_id=user.id).options(
                joinedload(Order.store),
                joinedload(Order.items).joinedload(OrderItem.product),
                joinedload(Order.delivery_person)
            ).order_by(Order.created_at.desc()).all()

            for order in all_orders:
                if order.status == 'delivered':
                    delivered_time = order.delivered_at or order.created_at
                    if delivered_time < cutoff:
                        continue
                orders.append(order)

    return render_template('customer/cart.html', grouped=grouped, orders=orders)

@cart_bp.route('/cart/count')
def cart_count():
    if 'user_id' in session:
        _merge_cart_with_db(session['user_id'], _get_session_cart())
        if db.session.dirty or db.session.new:
            db.session.commit()
    cart = _get_session_cart()
    return jsonify({'cart_count': sum(cart.values())})

@cart_bp.route('/api/cart/sync', methods=['POST'])
def sync_cart():
    data = request.get_json(silent=True) or {}
    local_cart = data.get('cart', {})
    if not isinstance(local_cart, dict):
        return jsonify({'status': 'error', 'message': 'بيانات غير صالحة'}), 400

    if 'user_id' in session:
        user_id = session['user_id']
        CartItem.query.filter_by(user_id=user_id).delete()
        for pid_str, qty in local_cart.items():
            try:
                product_id = int(pid_str)
                qty = int(qty)
                if qty < 1:
                    continue
                product = db.session.get(Product, product_id)
                if not product:
                    continue
                db.session.add(CartItem(
                    user_id=user_id,
                    product_id=product_id,
                    store_id=product.store_id,
                    quantity=min(qty, product.stock_quantity)
                ))
            except (ValueError, TypeError):
                continue
        db.session.commit()
        session['cart'] = {str(item.product_id): item.quantity for item in CartItem.query.filter_by(user_id=user_id).all()}
        session.modified = True
    else:
        session['cart'] = {str(k): int(v) for k, v in local_cart.items() if int(v) > 0}
        session.modified = True

    cart = _get_session_cart()
    return jsonify({'status': 'success', 'cart_count': sum(cart.values())})

@cart_bp.route('/cart/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    quantity = int(request.form.get('quantity', 1))
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

    cart[str(product_id)] = current_qty + quantity
    _save_session_cart(cart)

    if 'user_id' in session:
        user_id = session['user_id']
        existing = CartItem.query.filter_by(
            user_id=user_id, product_id=product_id
        ).first()
        if existing:
            existing.quantity = min(existing.quantity + quantity, product.stock_quantity)
        else:
            db.session.add(CartItem(
                user_id=user_id,
                product_id=product_id,
                store_id=product.store_id,
                quantity=min(quantity, product.stock_quantity)
            ))
        db.session.commit()
        db_items = CartItem.query.filter_by(user_id=user_id).all()
        session['cart'] = {str(item.product_id): item.quantity for item in db_items}

    cart = _get_session_cart()
    if is_ajax:
        return jsonify({'status': 'success', 'message': 'تمت الإضافة إلى السلة', 'cart_count': sum(cart.values())})
    flash('تمت الإضافة إلى السلة')
    next_url = safe_redirect_target(request.form.get('next'))
    if next_url:
        return redirect(next_url)
    return redirect(request.referrer or url_for('market.market'))

@cart_bp.route('/cart/update/<int:product_id>', methods=['POST'])
def update_cart(product_id):
    product = Product.query.get_or_404(product_id)
    action = request.form.get('action')
    cart = _get_session_cart()
    pid_str = str(product_id)
    is_ajax = _is_ajax()

    if action == 'remove':
        cart.pop(pid_str, None)
        if 'user_id' in session:
            CartItem.query.filter_by(
                user_id=session['user_id'], product_id=product_id
            ).delete()
            db.session.commit()
    else:
        new_qty = int(request.form.get('quantity', 1))
        if new_qty < 1:
            cart.pop(pid_str, None)
            if 'user_id' in session:
                CartItem.query.filter_by(
                    user_id=session['user_id'], product_id=product_id
                ).delete()
                db.session.commit()
        elif new_qty > product.stock_quantity:
            cart[pid_str] = product.stock_quantity
            if 'user_id' in session:
                existing = CartItem.query.filter_by(
                    user_id=session['user_id'], product_id=product_id
                ).first()
                if existing:
                    existing.quantity = product.stock_quantity
                    db.session.commit()
            _save_session_cart(cart)
            if is_ajax:
                return jsonify({'status': 'error', 'message': 'المخزون غير كافٍ', 'cart_count': sum(cart.values())}), 400
            flash('المخزون غير كافٍ', 'error')
            return redirect(request.referrer or url_for('cart.cart'))
        else:
            cart[pid_str] = new_qty
            if 'user_id' in session:
                existing = CartItem.query.filter_by(
                    user_id=session['user_id'], product_id=product_id
                ).first()
                if existing:
                    existing.quantity = new_qty
                else:
                    db.session.add(CartItem(
                        user_id=session['user_id'],
                        product_id=product_id,
                        store_id=product.store_id,
                        quantity=new_qty
                    ))
                db.session.commit()

    _save_session_cart(cart)

    if is_ajax:
        effective_price = OrderService.get_effective_price(product)
        item_total = effective_price * cart.get(pid_str, 0)
        return jsonify({
            'status': 'success',
            'cart_count': sum(cart.values()),
            'item_total': item_total,
            'quantity': cart.get(pid_str, 0)
        })
    return redirect(request.referrer or url_for('cart.cart'))

@cart_bp.route('/cart/remove/<int:product_id>', methods=['POST'])
def remove_from_cart(product_id):
    """إزالة منتج محدد من السلة (للجلسة وقاعدة البيانات)."""
    cart = _get_session_cart()
    pid_str = str(product_id)
    cart.pop(pid_str, None)
    _save_session_cart(cart)

    if 'user_id' in session:
        CartItem.query.filter_by(
            user_id=session['user_id'], product_id=product_id
        ).delete()
        db.session.commit()

    if _is_ajax():
        return jsonify({'status': 'success', 'message': 'تمت إزالة المنتج من السلة', 'cart_count': sum(cart.values())})
    flash('تمت إزالة المنتج من السلة', 'success')
    return redirect(request.referrer or url_for('cart.cart'))

@cart_bp.route('/cart/clear', methods=['POST'])
def clear_cart():
    session.pop('cart', None)
    if 'user_id' in session:
        CartItem.query.filter_by(user_id=session['user_id']).delete()
        db.session.commit()
    flash('تم مسح السلة بالكامل', 'success')
    return redirect(url_for('cart.cart'))

@cart_bp.route('/cart/clear/<int:store_id>', methods=['POST'])
def clear_store_cart(store_id):
    cart = _get_session_cart()
    if not cart:
        return redirect(url_for('cart.cart'))

    products = Product.query.filter(Product.store_id == store_id).all()
    for product in products:
        cart.pop(str(product.id), None)
        if 'user_id' in session:
            CartItem.query.filter_by(
                user_id=session['user_id'], product_id=product.id
            ).delete()
    if 'user_id' in session:
        db.session.commit()

    _save_session_cart(cart)
    flash('تم مسح منتجات هذا المتجر من السلة', 'success')
    return redirect(url_for('cart.cart'))

@cart_bp.route('/cart/checkout/<int:store_id>', methods=['GET'])
@login_required
def checkout(store_id):
    user = db.session.get(User, session['user_id'])
    if not user or not user.is_active:
        flash('الحساب محظور')
        return redirect(url_for('auth.login'))

    cart = _get_session_cart()
    if not cart:
        return redirect(url_for('cart.cart'))

    store = Store.query.get_or_404(store_id)

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

    product_total = sum(OrderService.get_effective_price(item['product']) * item['quantity'] for item in items)
    delivery_fee = float(get_setting('delivery_fee', 100)) if store.has_delivery else 0.0
    grand_total = product_total + delivery_fee

    all_stores = Store.query.filter(
        Store.subscription_status == 'active',
        Store.latitude.isnot(None),
        Store.longitude.isnot(None)
    ).all()

    return render_template('customer/checkout.html',
                           store=store,
                           items=items,
                           total=product_total,
                           delivery_fee=delivery_fee,
                           grand_total=grand_total,
                           all_stores=all_stores)

@cart_bp.route('/cart/checkout/<int:store_id>', methods=['POST'])
@login_required
def place_order(store_id):
    user = db.session.get(User, session['user_id'])
    if not user or not user.is_active:
        if request.is_json:
            return jsonify({'message': 'الحساب محظور'}), 403
        flash('الحساب محظور')
        return redirect(url_for('auth.login'))

    store = Store.query.get_or_404(store_id)

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
            options_selected = item.get('options_selected')  # إضافة دعم الخيارات
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
            for item in cart_items:
                cart.pop(str(item['product'].id), None)
                if 'user_id' in session:
                    CartItem.query.filter_by(
                        user_id=session['user_id'], product_id=item['product'].id
                    ).delete()
            if 'user_id' in session:
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
    user = db.session.get(User, session['user_id'])
    if not user or not user.is_active:
        flash('الحساب محظور')
        return redirect(url_for('auth.login'))

    product = Product.query.get_or_404(product_id)
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
    product_total = OrderService.get_effective_price(product) * quantity
    delivery_fee = float(get_setting('delivery_fee', 100)) if store.has_delivery else 0.0
    grand_total = product_total + delivery_fee

    return render_template('customer/checkout.html', store=store, items=items,
                           total=product_total, delivery_fee=delivery_fee, grand_total=grand_total)

@cart_bp.route('/cart/order/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    user_id = session.get('user_id')
    user = db.session.get(User, user_id)
    order = Order.query.get_or_404(order_id)

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
    user = db.session.get(User, session['user_id'])
    order = Order.query.get_or_404(order_id)

    if order.customer_id != user.id:
        abort(403)

    if order.status not in ['delivered', 'cancelled']:
        flash('لا يمكن حذف هذا الطلب في حالته الحالية', 'error')
        return redirect(url_for('cart.cart'))

    try:
        OrderItem.query.filter_by(order_id=order.id).delete()
        OrderStatusHistory.query.filter_by(order_id=order.id).delete()
        Payment.query.filter_by(order_id=order.id).delete()
        db.session.delete(order)
        db.session.commit()
        flash('تم حذف الطلب بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash('حدث خطأ أثناء حذف الطلب: ' + str(e), 'error')

    return redirect(url_for('cart.cart'))
