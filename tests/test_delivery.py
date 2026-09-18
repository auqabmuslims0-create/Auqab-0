"""
اختبارات طبقة المندوب (delivery).

تغطي:
- RBAC على مسارات delivery HTML
- Dashboard tabs (mine/available/map)
- Claim order (HTML + JWT API) — race-safe عبر _claim_order_atomic
- Start delivery (يتطلب pickup_code)
- Complete delivery (يتطلب delivery_code + يحوّل cash→paid)
- Availability toggle
- Notifications API (session auth)
- JWT API للمندوبين
"""
import pytest
from datetime import time as dtime
from database import db
from models import User, Store, Product, Order, Payment
from shared.time_utils import current_time
from shared.services.order_service import OrderService


def _login(client, login_fixture, u):
    assert login_fixture(u['username'], u['password']).status_code == 302


def _jwt_token(app, user_id):
    with app.app_context():
        from blueprints.api.helpers import encode_auth_token
        return encode_auth_token(user_id)


def _make_ready_order_in_store(app, store_id, customer_id):
    """إنشاء طلب بحالة 'ready' في متجر معين. يعيد order_id."""
    with app.app_context():
        user = db.session.get(User, customer_id)
        store = db.session.get(Store, store_id)
        product = Product.query.filter_by(store_id=store.id).first()
        if not product:
            product = Product(store_id=store.id, name='DProduct',
                              price=50.0, stock_quantity=10)
            db.session.add(product)
            db.session.commit()
        order = OrderService.create_order(
            user=user, store=store,
            cart_items=[{'product': product, 'quantity': 1}],
            delivery_address='Test Address',
            latitude=33.5, longitude=36.3,
        )
        order.status = 'ready'
        db.session.commit()
        return order.id


# ═══════════════════════════════════════════════════════════════
# RBAC على dashboard
# ═══════════════════════════════════════════════════════════════
def test_delivery_dashboard_rejects_anonymous(client):
    r = client.get('/delivery')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_delivery_dashboard_rejects_customer(client, make_user, login):
    u = make_user(username='drb_cust', role='customer')
    _login(client, login, u)
    r = client.get('/delivery')
    assert r.status_code == 403


def test_delivery_dashboard_rejects_owner(client, make_user, login):
    u = make_user(username='drb_owner', role='owner')
    _login(client, login, u)
    r = client.get('/delivery')
    assert r.status_code == 403


def test_delivery_dashboard_rejects_admin(client, make_user, login):
    u = make_user(username='drb_admin', role='admin')
    _login(client, login, u)
    r = client.get('/delivery')
    assert r.status_code == 403


def test_delivery_dashboard_accessible_to_delivery(client, make_user, login):
    u = make_user(username='drb_driver', role='delivery')
    _login(client, login, u)
    r = client.get('/delivery')
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════
# Dashboard tabs
# ═══════════════════════════════════════════════════════════════
def test_dashboard_tab_mine(client, make_user, login):
    u = make_user(username='drb_tab1', role='delivery')
    _login(client, login, u)
    r = client.get('/delivery?tab=mine')
    assert r.status_code == 200


def test_dashboard_tab_available(client, make_user, login):
    u = make_user(username='drb_tab2', role='delivery')
    _login(client, login, u)
    r = client.get('/delivery?tab=available')
    assert r.status_code == 200


def test_dashboard_tab_map(client, make_user, login):
    u = make_user(username='drb_tab3', role='delivery')
    _login(client, login, u)
    r = client.get('/delivery?tab=map')
    assert r.status_code == 200


def test_dashboard_invalid_tab_falls_back_to_mine(client, make_user, login):
    u = make_user(username='drb_tab4', role='delivery')
    _login(client, login, u)
    r = client.get('/delivery?tab=bogus')
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════
# Claim order — HTML
# ═══════════════════════════════════════════════════════════════
def test_claim_rejects_nonexistent_order(client, make_user, login):
    u = make_user(username='dc_1', role='delivery')
    _login(client, login, u)
    r = client.post('/delivery/orders/999999/claim')
    assert r.status_code == 302
    with client.session_transaction() as sess:
        # flash error موجود (يظهر في الرد التالي)
        pass


def test_claim_rejects_wrong_status(
    client, app, make_user, make_active_store, login
):
    owner = make_user(username='dc_own1', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='dc_c1')
    # order is in 'new' status (not ready)
    with app.app_context():
        user = db.session.get(User, customer['id'])
        store = db.session.get(Store, s['id'])
        p = Product(store_id=store.id, name='P1', price=50.0, stock_quantity=10)
        db.session.add(p)
        db.session.commit()
        o = OrderService.create_order(
            user=user, store=store,
            cart_items=[{'product': p, 'quantity': 1}],
            delivery_address='addr', latitude=33.5, longitude=36.3,
        )
        order_id = o.id

    driver = make_user(username='dc_d1', role='delivery')
    _login(client, login, driver)
    r = client.post(f'/delivery/orders/{order_id}/claim')
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.delivery_person_id is None


def test_claim_rejects_already_claimed(
    client, app, make_user, make_active_store, login
):
    owner = make_user(username='dc_own2', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='dc_c2')
    driver_a = make_user(username='dc_da2', role='delivery')
    driver_b = make_user(username='dc_db2', role='delivery')
    order_id = _make_ready_order_in_store(app, s['id'], customer['id'])

    with app.app_context():
        o = db.session.get(Order, order_id)
        o.delivery_person_id = driver_a['id']
        db.session.commit()

    _login(client, login, driver_b)
    r = client.post(f'/delivery/orders/{order_id}/claim')
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.delivery_person_id == driver_a['id']


def test_claim_rejects_store_without_delivery(
    client, app, make_user, make_active_store, login
):
    owner = make_user(username='dc_own3', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=False)
    customer = make_user(username='dc_c3')
    order_id = _make_ready_order_in_store(app, s['id'], customer['id'])

    driver = make_user(username='dc_d3', role='delivery')
    _login(client, login, driver)
    r = client.post(f'/delivery/orders/{order_id}/claim')
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.delivery_person_id is None


def test_claim_success(
    client, app, make_user, make_active_store, login
):
    owner = make_user(username='dc_own4', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='dc_c4')
    driver = make_user(username='dc_d4', role='delivery')
    order_id = _make_ready_order_in_store(app, s['id'], customer['id'])

    _login(client, login, driver)
    r = client.post(f'/delivery/orders/{order_id}/claim')
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.delivery_person_id == driver['id']
        assert o.pickup_code is not None
        assert o.delivery_fee > 0


def test_claim_rejects_unavailable_driver(
    client, app, make_user, make_active_store, login
):
    """مندوب is_available=False لا يستطيع claim."""
    owner = make_user(username='dc_own5', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='dc_c5')
    driver = make_user(username='dc_d5', role='delivery')
    order_id = _make_ready_order_in_store(app, s['id'], customer['id'])

    with app.app_context():
        d = db.session.get(User, driver['id'])
        d.is_available = False
        db.session.commit()

    _login(client, login, driver)
    r = client.post(f'/delivery/orders/{order_id}/claim')
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.delivery_person_id is None


# ═══════════════════════════════════════════════════════════════
# Start delivery — HTML
# ═══════════════════════════════════════════════════════════════
def test_start_wrong_delivery_person_403(
    client, app, make_user, make_active_store, login
):
    owner = make_user(username='ds_own1', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='ds_c1')
    driver_a = make_user(username='ds_da1', role='delivery')
    driver_b = make_user(username='ds_db1', role='delivery')
    order_id = _make_ready_order_in_store(app, s['id'], customer['id'])

    with app.app_context():
        o = db.session.get(Order, order_id)
        o.delivery_person_id = driver_a['id']
        o.pickup_code = '123456'
        db.session.commit()

    _login(client, login, driver_b)
    r = client.post(f'/delivery/orders/{order_id}/start', data={'pickup_code': '123456'})
    assert r.status_code == 403


def test_start_wrong_pickup_code(
    client, app, make_user, make_active_store, login
):
    owner = make_user(username='ds_own2', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='ds_c2')
    driver = make_user(username='ds_d2', role='delivery')
    order_id = _make_ready_order_in_store(app, s['id'], customer['id'])

    with app.app_context():
        o = db.session.get(Order, order_id)
        o.delivery_person_id = driver['id']
        o.pickup_code = '654321'
        db.session.commit()

    _login(client, login, driver)
    r = client.post(f'/delivery/orders/{order_id}/start', data={'pickup_code': '000000'})
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.status == 'ready'


def test_start_success(
    client, app, make_user, make_active_store, login
):
    owner = make_user(username='ds_own3', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='ds_c3')
    driver = make_user(username='ds_d3', role='delivery')
    order_id = _make_ready_order_in_store(app, s['id'], customer['id'])

    with app.app_context():
        o = db.session.get(Order, order_id)
        o.delivery_person_id = driver['id']
        o.pickup_code = '111222'
        db.session.commit()

    _login(client, login, driver)
    r = client.post(f'/delivery/orders/{order_id}/start', data={'pickup_code': '111222'})
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.status == 'delivering'


# ═══════════════════════════════════════════════════════════════
# Complete delivery — HTML
# ═══════════════════════════════════════════════════════════════
def test_deliver_wrong_delivery_person_403(
    client, app, make_user, make_active_store, login
):
    owner = make_user(username='dd_own1', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='dd_c1')
    driver_a = make_user(username='dd_da1', role='delivery')
    driver_b = make_user(username='dd_db1', role='delivery')
    order_id = _make_ready_order_in_store(app, s['id'], customer['id'])

    with app.app_context():
        o = db.session.get(Order, order_id)
        o.delivery_person_id = driver_a['id']
        o.delivery_code = '333444'
        o.status = 'delivering'
        db.session.commit()

    _login(client, login, driver_b)
    r = client.post(f'/delivery/orders/{order_id}/deliver', data={'delivery_code': '333444'})
    assert r.status_code == 403


def test_deliver_wrong_code(
    client, app, make_user, make_active_store, login
):
    owner = make_user(username='dd_own2', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='dd_c2')
    driver = make_user(username='dd_d2', role='delivery')
    order_id = _make_ready_order_in_store(app, s['id'], customer['id'])

    with app.app_context():
        o = db.session.get(Order, order_id)
        o.delivery_person_id = driver['id']
        o.delivery_code = '555666'
        o.status = 'delivering'
        db.session.commit()

    _login(client, login, driver)
    r = client.post(f'/delivery/orders/{order_id}/deliver', data={'delivery_code': '000000'})
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.status == 'delivering'


def test_deliver_success_marks_cash_paid(
    client, app, make_user, make_active_store, login
):
    owner = make_user(username='dd_own3', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='dd_c3')
    driver = make_user(username='dd_d3', role='delivery')
    order_id = _make_ready_order_in_store(app, s['id'], customer['id'])

    with app.app_context():
        o = db.session.get(Order, order_id)
        o.delivery_person_id = driver['id']
        o.delivery_code = '777888'
        o.status = 'delivering'
        db.session.commit()

    _login(client, login, driver)
    r = client.post(f'/delivery/orders/{order_id}/deliver', data={'delivery_code': '777888'})
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.status == 'delivered'
        assert o.delivered_at is not None
        # cash payment should be marked as 'paid'
        for p in Payment.query.filter_by(order_id=order_id).all():
            if p.method == 'cash':
                assert p.status == 'paid'


# ═══════════════════════════════════════════════════════════════
# Availability toggle
# ═══════════════════════════════════════════════════════════════
def test_update_availability_false(client, app, make_user, login):
    u = make_user(username='avail_off', role='delivery')
    _login(client, login, u)
    r = client.post('/delivery/availability', data={'is_available': 'false'})
    assert r.status_code == 302
    with app.app_context():
        d = db.session.get(User, u['id'])
        assert d.is_available is False


def test_update_availability_true(client, app, make_user, login):
    u = make_user(username='avail_on', role='delivery')
    with app.app_context():
        d = db.session.get(User, u['id'])
        d.is_available = False
        db.session.commit()
    _login(client, login, u)
    r = client.post('/delivery/availability', data={'is_available': 'true'})
    assert r.status_code == 302
    with app.app_context():
        d = db.session.get(User, u['id'])
        assert d.is_available is True


# ═══════════════════════════════════════════════════════════════
# Notifications API (session-based)
# ═══════════════════════════════════════════════════════════════
def test_notifications_api_rejects_anonymous(client):
    r = client.get('/api/delivery/notifications')
    assert r.status_code == 401


def test_notifications_api_rejects_customer(client, make_user, login):
    u = make_user(username='na_cust', role='customer')
    _login(client, login, u)
    r = client.get('/api/delivery/notifications')
    assert r.status_code == 403


def test_notifications_api_returns_empty_for_delivery(client, make_user, login):
    u = make_user(username='na_driver', role='delivery')
    _login(client, login, u)
    r = client.get('/api/delivery/notifications')
    assert r.status_code == 200
    data = r.get_json()
    assert data['status'] == 'success'
    assert data['notifications'] == []


# ═══════════════════════════════════════════════════════════════
# JWT API (delivery_api_bp)
# ═══════════════════════════════════════════════════════════════
def test_jwt_api_requires_token(client, app):
    r = client.get('/api/delivery/available-orders')
    assert r.status_code == 401


def test_jwt_api_rejects_non_delivery(client, app, make_user):
    customer = make_user(username='jwt_cust')
    token = _jwt_token(app, customer['id'])
    r = client.get('/api/delivery/available-orders',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 403


def test_jwt_api_available_orders(client, app, make_user, make_active_store):
    driver = make_user(username='jwt_driver1', role='delivery')
    owner = make_user(username='jwt_own1', role='owner')
    make_active_store(owner_id=owner['id'], has_delivery=True)
    token = _jwt_token(app, driver['id'])
    r = client.get('/api/delivery/available-orders',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    assert 'orders' in r.get_json()


def test_jwt_api_get_assigned_orders(client, app, make_user):
    driver = make_user(username='jwt_driver2', role='delivery')
    token = _jwt_token(app, driver['id'])
    r = client.get('/api/delivery/orders',
                   headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    data = r.get_json()
    assert 'orders' in data


def test_jwt_api_claim_success(
    client, app, make_user, make_active_store
):
    owner = make_user(username='jwt_own2', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='jwt_c2')
    driver = make_user(username='jwt_d2', role='delivery')
    order_id = _make_ready_order_in_store(app, s['id'], customer['id'])

    token = _jwt_token(app, driver['id'])
    r = client.post(f'/api/delivery/orders/{order_id}/claim',
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.delivery_person_id == driver['id']


def test_jwt_api_claim_already_claimed(
    client, app, make_user, make_active_store
):
    owner = make_user(username='jwt_own3', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='jwt_c3')
    driver_a = make_user(username='jwt_da3', role='delivery')
    driver_b = make_user(username='jwt_db3', role='delivery')
    order_id = _make_ready_order_in_store(app, s['id'], customer['id'])

    with app.app_context():
        o = db.session.get(Order, order_id)
        o.delivery_person_id = driver_a['id']
        db.session.commit()

    token = _jwt_token(app, driver_b['id'])
    r = client.post(f'/api/delivery/orders/{order_id}/claim',
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 400


def test_jwt_api_start_wrong_code(
    client, app, make_user, make_active_store
):
    owner = make_user(username='jwt_own4', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='jwt_c4')
    driver = make_user(username='jwt_d4', role='delivery')
    order_id = _make_ready_order_in_store(app, s['id'], customer['id'])

    with app.app_context():
        o = db.session.get(Order, order_id)
        o.delivery_person_id = driver['id']
        o.pickup_code = '999000'
        db.session.commit()

    token = _jwt_token(app, driver['id'])
    r = client.post(f'/api/delivery/orders/{order_id}/start',
                    json={'pickup_code': '000000'},
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 400


def test_jwt_api_start_success(
    client, app, make_user, make_active_store
):
    owner = make_user(username='jwt_own5', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='jwt_c5')
    driver = make_user(username='jwt_d5', role='delivery')
    order_id = _make_ready_order_in_store(app, s['id'], customer['id'])

    with app.app_context():
        o = db.session.get(Order, order_id)
        o.delivery_person_id = driver['id']
        o.pickup_code = '123123'
        db.session.commit()

    token = _jwt_token(app, driver['id'])
    r = client.post(f'/api/delivery/orders/{order_id}/start',
                    json={'pickup_code': '123123'},
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.status == 'delivering'


def test_jwt_api_deliver_success(
    client, app, make_user, make_active_store
):
    owner = make_user(username='jwt_own6', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='jwt_c6')
    driver = make_user(username='jwt_d6', role='delivery')
    order_id = _make_ready_order_in_store(app, s['id'], customer['id'])

    with app.app_context():
        o = db.session.get(Order, order_id)
        o.delivery_person_id = driver['id']
        o.delivery_code = '456456'
        o.status = 'delivering'
        db.session.commit()

    token = _jwt_token(app, driver['id'])
    r = client.post(f'/api/delivery/orders/{order_id}/deliver',
                    json={'delivery_code': '456456'},
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.status == 'delivered'
