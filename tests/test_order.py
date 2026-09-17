"""اختبارات الطلب: create, cancel, delete, totals."""
from datetime import timedelta
from database import db
from models import Order, Payment
from shared.services.order_service import OrderService
from shared.time_utils import current_time


def _login(client, login_fixture, u):
    r = login_fixture(u['username'], u['password'])
    assert r.status_code == 302


# ═══════════════════════════════════════════════════════════════
# compute_order_totals
# ═══════════════════════════════════════════════════════════════
def test_compute_totals_no_delivery(app, make_active_store, make_product):
    with app.app_context():
        s = make_active_store(has_delivery=False)
        p = make_product(s['id'], price=100.0, stock=10)
        from models import Store, Product
        store = db.session.get(Store, s['id'])
        product = db.session.get(Product, p['id'])
        totals = OrderService.compute_order_totals(
            store, [{'product': product, 'quantity': 3}]
        )
        assert totals['product_total'] == 300.0
        assert totals['delivery_fee'] == 0.0
        assert totals['grand_total'] == 300.0


def test_compute_totals_with_delivery(app, make_active_store, make_product):
    with app.app_context():
        s = make_active_store(has_delivery=True)
        p = make_product(s['id'], price=100.0, stock=10)
        from models import Store, Product
        store = db.session.get(Store, s['id'])
        product = db.session.get(Product, p['id'])
        totals = OrderService.compute_order_totals(
            store, [{'product': product, 'quantity': 2}]
        )
        assert totals['product_total'] == 200.0
        assert totals['delivery_fee'] > 0  # يأتي من get_setting
        assert totals['grand_total'] == totals['product_total'] + totals['delivery_fee']


# ═══════════════════════════════════════════════════════════════
# create_order (مباشر عبر الخدمة)
# ═══════════════════════════════════════════════════════════════
def test_create_order_minimal(app, make_user, make_active_store, make_product):
    with app.app_context():
        u = make_user(username='order1')
        s = make_active_store(has_delivery=False)
        p = make_product(s['id'], price=50.0, stock=10)
        from models import User, Store, Product
        user = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        product = db.session.get(Product, p['id'])
        order = OrderService.create_order(
            user=user, store=store,
            cart_items=[{'product': product, 'quantity': 2}],
        )
        assert order.id is not None
        assert order.total == 100.0
        assert order.delivery_fee == 0.0
        assert order.status == 'new'
        # المخزون انخفض
        db.session.refresh(product)
        assert product.stock_quantity == 8
        # Payment أُنشئ
        payments = Payment.query.filter_by(order_id=order.id).all()
        assert len(payments) == 1
        assert payments[0].amount == 100.0


def test_create_order_rejects_hidden_price(app, make_user, make_active_store, make_product):
    with app.app_context():
        u = make_user(username='order2')
        s = make_active_store(has_delivery=False)
        p = make_product(s['id'], hide_price=True, stock=5)
        from models import User, Store, Product
        user = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        product = db.session.get(Product, p['id'])
        try:
            OrderService.create_order(
                user=user, store=store,
                cart_items=[{'product': product, 'quantity': 1}],
            )
            assert False, 'كان يجب أن يفشل'
        except ValueError as e:
            assert 'حصراً من المتجر' in str(e)


def test_create_order_rejects_insufficient_stock(app, make_user, make_active_store, make_product):
    with app.app_context():
        u = make_user(username='order3')
        s = make_active_store(has_delivery=False)
        p = make_product(s['id'], stock=2)
        from models import User, Store, Product
        user = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        product = db.session.get(Product, p['id'])
        try:
            OrderService.create_order(
                user=user, store=store,
                cart_items=[{'product': product, 'quantity': 5}],
            )
            assert False, 'كان يجب أن يفشل'
        except ValueError as e:
            assert 'المخزون' in str(e)


def test_create_order_requires_delivery_address(app, make_user, make_active_store, make_product):
    with app.app_context():
        u = make_user(username='order4')
        s = make_active_store(has_delivery=True)
        p = make_product(s['id'], stock=5)
        from models import User, Store, Product
        user = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        product = db.session.get(Product, p['id'])
        try:
            OrderService.create_order(
                user=user, store=store,
                cart_items=[{'product': product, 'quantity': 1}],
            )
            assert False, 'كان يجب أن يفشل'
        except ValueError as e:
            assert 'العنوان' in str(e)


# ═══════════════════════════════════════════════════════════════
# cancel_order
# ═══════════════════════════════════════════════════════════════
def test_cancel_order_restores_stock(app, make_user, make_active_store, make_product):
    with app.app_context():
        u = make_user(username='canceller')
        s = make_active_store(has_delivery=False)
        p = make_product(s['id'], stock=10)
        from models import User, Store, Product
        user = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        product = db.session.get(Product, p['id'])
        order = OrderService.create_order(
            user=user, store=store,
            cart_items=[{'product': product, 'quantity': 3}],
        )
        OrderService.cancel_order(user, order)
        db.session.refresh(product)
        assert product.stock_quantity == 10
        assert order.status == 'cancelled'
        assert order.is_cancelled is True


def test_cancel_order_denies_other_user(app, make_user, make_active_store, make_product):
    with app.app_context():
        u1 = make_user(username='c1')
        u2 = make_user(username='c2')
        s = make_active_store(has_delivery=False)
        p = make_product(s['id'], stock=10)
        from models import User, Store, Product
        user1 = db.session.get(User, u1['id'])
        user2 = db.session.get(User, u2['id'])
        store = db.session.get(Store, s['id'])
        product = db.session.get(Product, p['id'])
        order = OrderService.create_order(
            user=user1, store=store,
            cart_items=[{'product': product, 'quantity': 1}],
        )
        try:
            OrderService.cancel_order(user2, order)
            assert False, 'كان يجب أن يفشل'
        except PermissionError:
            pass


def test_cancel_order_rejects_delivered(app, make_user, make_active_store, make_product):
    with app.app_context():
        u = make_user(username='c3')
        s = make_active_store(has_delivery=False)
        p = make_product(s['id'], stock=10)
        from models import User, Store, Product
        user = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        product = db.session.get(Product, p['id'])
        order = OrderService.create_order(
            user=user, store=store,
            cart_items=[{'product': product, 'quantity': 1}],
        )
        order.status = 'delivered'
        db.session.commit()
        try:
            OrderService.cancel_order(user, order)
            assert False, 'كان يجب أن يفشل'
        except ValueError:
            pass


# ═══════════════════════════════════════════════════════════════
# delete_order
# ═══════════════════════════════════════════════════════════════
def test_delete_order_allowed_for_cancelled(app, make_user, make_active_store, make_product):
    with app.app_context():
        u = make_user(username='deleter')
        s = make_active_store(has_delivery=False)
        p = make_product(s['id'], stock=10)
        from models import User, Store, Product
        user = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        product = db.session.get(Product, p['id'])
        order = OrderService.create_order(
            user=user, store=store,
            cart_items=[{'product': product, 'quantity': 1}],
        )
        OrderService.cancel_order(user, order)
        order_id = order.id
        OrderService.delete_order(user, order)
        assert db.session.get(Order, order_id) is None


def test_delete_order_rejects_new_status(app, make_user, make_active_store, make_product):
    with app.app_context():
        u = make_user(username='deleter2')
        s = make_active_store(has_delivery=False)
        p = make_product(s['id'], stock=10)
        from models import User, Store, Product
        user = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        product = db.session.get(Product, p['id'])
        order = OrderService.create_order(
            user=user, store=store,
            cart_items=[{'product': product, 'quantity': 1}],
        )
        # order.status == 'new'
        try:
            OrderService.delete_order(user, order)
            assert False, 'كان يجب أن يفشل'
        except ValueError as e:
            assert 'لا يمكن حذف' in str(e)


def test_delete_order_denies_other_user(app, make_user, make_active_store, make_product):
    with app.app_context():
        u1 = make_user(username='o1')
        u2 = make_user(username='o2')
        s = make_active_store(has_delivery=False)
        p = make_product(s['id'], stock=10)
        from models import User, Store, Product
        user1 = db.session.get(User, u1['id'])
        user2 = db.session.get(User, u2['id'])
        store = db.session.get(Store, s['id'])
        product = db.session.get(Product, p['id'])
        order = OrderService.create_order(
            user=user1, store=store,
            cart_items=[{'product': product, 'quantity': 1}],
        )
        order.status = 'cancelled'
        db.session.commit()
        try:
            OrderService.delete_order(user2, order)
            assert False, 'كان يجب أن يفشل'
        except PermissionError:
            pass


# ═══════════════════════════════════════════════════════════════
# place_order عبر HTTP
# ═══════════════════════════════════════════════════════════════
def test_place_order_via_http(client, app, make_user, login,
                              make_active_store, make_product):
    u = make_user(username='htt buyer'.replace(' ', ''))
    _login(client, login, u)
    s = make_active_store(has_delivery=False)
    p = make_product(s['id'], price=75.0, stock=10)
    # add to cart
    client.post(f'/cart/add/{p["id"]}', data={'quantity': '2'})
    # place order
    r = client.post(f'/cart/checkout/{s["id"]}', data={})
    assert r.status_code == 302
    with app.app_context():
        order = Order.query.filter_by(customer_id=u['id']).first()
        assert order is not None
        assert order.total == 150.0
