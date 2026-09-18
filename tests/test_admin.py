"""
اختبارات مسارات الإدارة (Admin).

تغطي:
- RBAC على 8 مسارات admin × 4 أدوار (customer/owner/delivery/admin)
- إدارة المستخدمين (list, filter, toggle, reset password, delete, contact)
- إدارة المتاجر (list, filter, toggle)
- إدارة الطلبات (list, filter)
- إدارة الاشتراكات (list, filter, approve, reject, extend)
- إدارة مندوبي التوصيل (create, edit, toggle, delete, shift)
- التقارير المالية والمدفوعات
"""
from datetime import timedelta
import pytest
from database import db
from models import User, Store, Order, Subscription, Payment, Notification
from shared.time_utils import current_time


def _login(client, login_fixture, u):
    assert login_fixture(u['username'], u['password']).status_code == 302


ADMIN_PATHS = [
    '/admin',
    '/admin/users',
    '/admin/orders',
    '/admin/stores',
    '/admin/subscriptions',
    '/admin/finance',
    '/admin/payments',
    '/admin/delivery_persons',
]


# ═══════════════════════════════════════════════════════════════
# RBAC — كل مسارات admin محمية بـ @role_required('admin')
# ═══════════════════════════════════════════════════════════════
@pytest.mark.parametrize('path', ADMIN_PATHS)
def test_admin_paths_reject_anonymous(client, path):
    r = client.get(path)
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


@pytest.mark.parametrize('path', ADMIN_PATHS)
def test_admin_paths_reject_customer(client, path, make_user, login):
    u = make_user(username='rbac_cust', role='customer')
    _login(client, login, u)
    r = client.get(path)
    assert r.status_code == 403


@pytest.mark.parametrize('path', ADMIN_PATHS)
def test_admin_paths_reject_owner(client, path, make_user, login):
    u = make_user(username='rbac_owner', role='owner')
    _login(client, login, u)
    r = client.get(path)
    assert r.status_code == 403


@pytest.mark.parametrize('path', ADMIN_PATHS)
def test_admin_paths_reject_delivery(client, path, make_user, login):
    u = make_user(username='rbac_del', role='delivery')
    _login(client, login, u)
    r = client.get(path)
    assert r.status_code == 403


@pytest.mark.parametrize('path', ADMIN_PATHS)
def test_admin_paths_accessible_to_admin(client, path, make_user, login):
    u = make_user(username='rbac_admin', role='admin')
    _login(client, login, u)
    r = client.get(path)
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════
# إدارة المستخدمين
# ═══════════════════════════════════════════════════════════════
def test_admin_users_list(client, make_user, login):
    admin = make_user(username='a_users1', role='admin')
    make_user(username='target_alpha')
    make_user(username='target_beta')
    _login(client, login, admin)
    r = client.get('/admin/users')
    assert r.status_code == 200
    body = r.data.decode('utf-8')
    assert 'target_alpha' in body
    assert 'target_beta' in body


def test_admin_users_filter_by_role(client, make_user, login):
    admin = make_user(username='a_users2', role='admin')
    make_user(username='filter_cust', role='customer')
    make_user(username='filter_owner', role='owner')
    _login(client, login, admin)
    r = client.get('/admin/users?role=owner')
    assert r.status_code == 200
    body = r.data.decode('utf-8')
    assert 'filter_owner' in body
    assert 'filter_cust' not in body


def test_admin_users_search(client, make_user, login):
    admin = make_user(username='a_users3', role='admin')
    make_user(username='uniquename_xyz')
    make_user(username='other_user')
    _login(client, login, admin)
    r = client.get('/admin/users?q=uniquename_xyz')
    assert r.status_code == 200
    body = r.data.decode('utf-8')
    assert 'uniquename_xyz' in body
    assert 'other_user' not in body


def test_admin_toggle_user_deactivates(client, app, make_user, login):
    admin = make_user(username='a_users4', role='admin')
    target = make_user(username='victim_toggle')
    _login(client, login, admin)
    r = client.post(f'/admin/users/{target["id"]}/toggle')
    assert r.status_code == 302
    with app.app_context():
        u = db.session.get(User, target['id'])
        assert u.is_active is False


def test_admin_toggle_user_activates(client, app, make_user, login):
    admin = make_user(username='a_users5', role='admin')
    target = make_user(username='victim_react', is_active=False)
    _login(client, login, admin)
    r = client.post(f'/admin/users/{target["id"]}/toggle')
    assert r.status_code == 302
    with app.app_context():
        u = db.session.get(User, target['id'])
        assert u.is_active is True


def test_admin_toggle_user_prevents_self(client, app, make_user, login):
    admin = make_user(username='a_users6', role='admin')
    _login(client, login, admin)
    r = client.post(f'/admin/users/{admin["id"]}/toggle')
    assert r.status_code == 302
    with app.app_context():
        u = db.session.get(User, admin['id'])
        assert u.is_active is True


def test_admin_reset_password_creates_temp(client, app, make_user, login):
    admin = make_user(username='a_users7', role='admin')
    target = make_user(username='victim_reset')
    _login(client, login, admin)
    r = client.post(f'/admin/users/{target["id"]}/reset_password')
    assert r.status_code == 302
    # temp password stored in session (not in flash)
    with client.session_transaction() as sess:
        temp = sess.get('reset_password_temp')
        assert temp is not None
        assert len(temp) >= 8


def test_admin_delete_user_with_relations_cascades(
    client, app, make_user, make_store, make_product, login
):
    """حذف مالك متجر يحذف المتجر ومنتجاته."""
    admin = make_user(username='a_users8', role='admin')
    owner = make_user(username='victim_owner', role='owner')
    s = make_store(owner_id=owner['id'])
    make_product(s['id'])
    owner_id = owner['id']
    store_id = s['id']

    _login(client, login, admin)
    r = client.post(f'/admin/users/{owner_id}/delete')
    assert r.status_code == 302

    with app.app_context():
        assert db.session.get(User, owner_id) is None
        assert db.session.get(Store, store_id) is None


def test_admin_delete_prevents_self(client, app, make_user, login):
    admin = make_user(username='a_users9', role='admin')
    _login(client, login, admin)
    r = client.post(f'/admin/users/{admin["id"]}/delete')
    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(User, admin['id']) is not None


def test_admin_contact_user_creates_notification(
    client, app, make_user, login
):
    admin = make_user(username='a_users10', role='admin')
    target = make_user(username='victim_contact')
    _login(client, login, admin)
    r = client.post(f'/admin/users/{target["id"]}/contact', data={
        'title': 'عنوان تجريبي',
        'message': 'نص الرسالة الإدارية'
    })
    assert r.status_code == 302
    with app.app_context():
        notif = Notification.query.filter_by(user_id=target['id']).first()
        assert notif is not None
        assert notif.title == 'عنوان تجريبي'


def test_admin_contact_user_rejects_empty(client, make_user, login):
    admin = make_user(username='a_users11', role='admin')
    target = make_user(username='victim_empty')
    _login(client, login, admin)
    r = client.post(f'/admin/users/{target["id"]}/contact', data={
        'title': '', 'message': ''
    })
    assert r.status_code == 302  # redirect back with flash


# ═══════════════════════════════════════════════════════════════
# إدارة المتاجر
# ═══════════════════════════════════════════════════════════════
def test_admin_stores_list(client, make_user, make_store, login):
    admin = make_user(username='a_stores1', role='admin')
    make_store(name='ListedStore')
    _login(client, login, admin)
    r = client.get('/admin/stores')
    assert r.status_code == 200
    assert b'ListedStore' in r.data


def test_admin_stores_filter_by_status(client, make_user, make_store, login):
    admin = make_user(username='a_stores2', role='admin')
    make_store(name='ActiveStoreX', subscription_status='active')
    make_store(name='SuspendedStoreX', subscription_status='suspended')
    _login(client, login, admin)
    r = client.get('/admin/stores?status=suspended')
    assert r.status_code == 200
    assert b'SuspendedStoreX' in r.data
    assert b'ActiveStoreX' not in r.data


def test_admin_toggle_store_suspends(client, app, make_user, make_store, login):
    admin = make_user(username='a_stores3', role='admin')
    s = make_store(subscription_status='active')
    _login(client, login, admin)
    r = client.post(f'/admin/stores/{s["id"]}/toggle', data={'action': 'suspend'})
    assert r.status_code == 302
    with app.app_context():
        store = db.session.get(Store, s['id'])
        assert store.subscription_status == 'suspended'


def test_admin_toggle_store_activate_force(client, app, make_user, make_store, login):
    admin = make_user(username='a_stores4', role='admin')
    s = make_store(subscription_status='suspended')
    _login(client, login, admin)
    r = client.post(f'/admin/stores/{s["id"]}/toggle', data={'action': 'activate'})
    assert r.status_code == 302
    with app.app_context():
        store = db.session.get(Store, s['id'])
        assert store.subscription_status == 'active'


def test_admin_store_subscription_settings(client, app, make_user, make_store, login):
    admin = make_user(username='a_stores5', role='admin')
    s = make_store()
    _login(client, login, admin)
    r = client.post(f'/admin/stores/{s["id"]}/subscription/settings', data={
        'custom_subscription_price': '750',
        'custom_subscription_duration_days': '45',
        'subscription_grace_days': '7',
        'subscription_notes': 'ملاحظة',
        'auto_renew': '1',
    })
    assert r.status_code == 302
    with app.app_context():
        store = db.session.get(Store, s['id'])
        assert store.custom_subscription_price == 750.0
        assert store.custom_subscription_duration_days == 45
        assert store.subscription_grace_days == 7
        assert store.auto_renew is True


# ═══════════════════════════════════════════════════════════════
# إدارة الطلبات
# ═══════════════════════════════════════════════════════════════
def test_admin_orders_list(client, make_user, make_store, login):
    admin = make_user(username='a_orders1', role='admin')
    make_store()
    _login(client, login, admin)
    r = client.get('/admin/orders')
    assert r.status_code == 200


def test_admin_orders_filter_by_status(
    client, app, make_user, make_active_store, make_product, login
):
    from shared.services.order_service import OrderService
    admin = make_user(username='a_orders2', role='admin')
    customer = make_user(username='cust_orders2')
    s = make_active_store(has_delivery=False)
    p = make_product(s['id'], stock=10)

    with app.app_context():
        user = db.session.get(User, customer['id'])
        store = db.session.get(Store, s['id'])
        from models import Product
        product = db.session.get(Product, p['id'])
        OrderService.create_order(user=user, store=store, cart_items=[
            {'product': product, 'quantity': 1}
        ])

    _login(client, login, admin)
    r = client.get('/admin/orders?status=new')
    assert r.status_code == 200


def test_admin_update_order_status_respects_transitions(
    client, app, make_user, make_active_store, make_product, login
):
    from shared.services.order_service import OrderService
    from models import Product
    admin = make_user(username='a_orders3', role='admin')
    customer = make_user(username='cust_orders3')
    s = make_active_store(has_delivery=False)
    p = make_product(s['id'], stock=10)

    with app.app_context():
        user = db.session.get(User, customer['id'])
        store = db.session.get(Store, s['id'])
        product = db.session.get(Product, p['id'])
        order = OrderService.create_order(user=user, store=store, cart_items=[
            {'product': product, 'quantity': 1}
        ])
        order_id = order.id

    _login(client, login, admin)
    # new → delivered غير مسموح
    r = client.post(f'/admin/orders/{order_id}/status', data={'status': 'delivered'})
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.status == 'new'

    # new → confirmed مسموح
    r = client.post(f'/admin/orders/{order_id}/status', data={'status': 'confirmed'})
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.status == 'confirmed'


# ═══════════════════════════════════════════════════════════════
# إدارة الاشتراكات
# ═══════════════════════════════════════════════════════════════
def _make_pending_sub(app, make_user, make_store):
    """إنشاء اشتراك pending للمتجر. يعيد (sub_id, store_id)."""
    owner = make_user(username=f'owner_{__import__("secrets").token_hex(3)}', role='owner')
    s = make_store(owner_id=owner['id'], subscription_status='pending')
    sub = Subscription(
        user_id=owner['id'],
        store_id=s['id'],
        start_date=current_time(),
        end_date=current_time() + timedelta(days=30),
        amount=500.0,
        status='pending',
        duration_days=30,
    )
    db.session.add(sub)
    db.session.commit()
    return sub.id, s['id']


def test_admin_subscriptions_list(client, make_user, login):
    admin = make_user(username='a_subs1', role='admin')
    _login(client, login, admin)
    r = client.get('/admin/subscriptions')
    assert r.status_code == 200


def test_admin_approve_subscription(client, app, make_user, make_store, login):
    admin = make_user(username='a_subs2', role='admin')
    with app.app_context():
        sub_id, store_id = _make_pending_sub(app, make_user, make_store)
    _login(client, login, admin)
    r = client.post(f'/admin/subscriptions/{sub_id}/approve')
    assert r.status_code == 302
    with app.app_context():
        sub = db.session.get(Subscription, sub_id)
        store = db.session.get(Store, store_id)
        assert sub.status == 'paid'
        assert store.subscription_status == 'active'


def test_admin_reject_subscription(client, app, make_user, make_store, login):
    admin = make_user(username='a_subs3', role='admin')
    with app.app_context():
        sub_id, store_id = _make_pending_sub(app, make_user, make_store)
    _login(client, login, admin)
    r = client.post(f'/admin/subscriptions/{sub_id}/reject', data={
        'admin_note': 'مرفوض'
    })
    assert r.status_code == 302
    with app.app_context():
        sub = db.session.get(Subscription, sub_id)
        assert sub.status == 'cancelled'


def test_admin_extend_subscription(client, app, make_user, make_store, login):
    admin = make_user(username='a_subs4', role='admin')
    with app.app_context():
        sub_id, _ = _make_pending_sub(app, make_user, make_store)
        # approve first
        from shared.services.subscription_service import SubscriptionService
        SubscriptionService.approve_subscription(sub_id)
        sub = db.session.get(Subscription, sub_id)
        original_end = sub.end_date

    _login(client, login, admin)
    r = client.post(f'/admin/subscriptions/{sub_id}/extend', data={'days': '15'})
    assert r.status_code == 302
    with app.app_context():
        sub = db.session.get(Subscription, sub_id)
        assert sub.end_date == original_end + timedelta(days=15)


# ═══════════════════════════════════════════════════════════════
# إدارة مندوبي التوصيل
# ═══════════════════════════════════════════════════════════════
def test_admin_delivery_persons_list(client, make_user, login):
    admin = make_user(username='a_del1', role='admin')
    make_user(username='driver_listed', role='delivery')
    _login(client, login, admin)
    r = client.get('/admin/delivery_persons')
    assert r.status_code == 200
    assert b'driver_listed' in r.data


def test_admin_create_delivery_person(client, app, make_user, login):
    admin = make_user(username='a_del2', role='admin')
    _login(client, login, admin)
    r = client.post('/admin/delivery_persons/new', data={
        'username': 'newdriver_x',
        'email': 'newdriver_x@test.local',
        'phone': '912345678',
        'password': 'StrongPass123!@#',
    })
    assert r.status_code == 302
    with app.app_context():
        d = User.query.filter_by(username='newdriver_x').first()
        assert d is not None
        assert d.role == 'delivery'
        assert d.phone == '+963912345678'


def test_admin_create_delivery_person_rejects_weak_password(client, app, make_user, login):
    admin = make_user(username='a_del3', role='admin')
    _login(client, login, admin)
    r = client.post('/admin/delivery_persons/new', data={
        'username': 'weakpass_driver',
        'email': 'weakpass@test.local',
        'phone': '912345679',
        'password': '123',
    })
    assert r.status_code == 302
    with app.app_context():
        d = User.query.filter_by(username='weakpass_driver').first()
        assert d is None


def test_admin_shift_edit_404_for_non_delivery(client, make_user, login):
    admin = make_user(username='a_del4', role='admin')
    customer = make_user(username='not_a_driver')
    _login(client, login, admin)
    r = client.get(f'/admin/delivery_persons/{customer["id"]}/shift')
    assert r.status_code == 404


def test_admin_shift_edit_updates(client, app, make_user, login):
    admin = make_user(username='a_del5', role='admin')
    driver = make_user(username='driver_shift', role='delivery')
    _login(client, login, admin)
    r = client.post(f'/admin/delivery_persons/{driver["id"]}/shift', data={
        'shift_start_time': '08:00',
        'shift_end_time': '16:00',
        'max_active_orders': '5',
    })
    assert r.status_code == 302
    with app.app_context():
        d = db.session.get(User, driver['id'])
        assert d.shift_start_time.strftime('%H:%M') == '08:00'
        assert d.shift_end_time.strftime('%H:%M') == '16:00'
        assert d.max_active_orders == 5


def test_admin_toggle_delivery_person(client, app, make_user, login):
    admin = make_user(username='a_del6', role='admin')
    driver = make_user(username='driver_toggle', role='delivery')
    _login(client, login, admin)
    r = client.post(f'/admin/delivery_persons/{driver["id"]}/toggle')
    assert r.status_code == 302
    with app.app_context():
        d = db.session.get(User, driver['id'])
        assert d.is_active is False


def test_admin_delete_delivery_person(client, app, make_user, login):
    admin = make_user(username='a_del7', role='admin')
    driver = make_user(username='driver_delete', role='delivery')
    driver_id = driver['id']
    _login(client, login, admin)
    r = client.post(f'/admin/delivery_persons/{driver_id}/delete')
    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(User, driver_id) is None


# ═══════════════════════════════════════════════════════════════
# المدفوعات
# ═══════════════════════════════════════════════════════════════
def test_admin_payments_list(client, app, make_user, make_store, login):
    admin = make_user(username='a_pay1', role='admin')
    s = make_store()
    with app.app_context():
        p = Payment(
            user_id=admin['id'],
            store_id=s['id'],
            amount=100.0,
            method='cash',
            status='pending',
        )
        db.session.add(p)
        db.session.commit()

    _login(client, login, admin)
    r = client.get('/admin/payments')
    assert r.status_code == 200


def test_admin_update_payment_status(client, app, make_user, make_store, login):
    admin = make_user(username='a_pay2', role='admin')
    s = make_store()
    with app.app_context():
        p = Payment(
            user_id=admin['id'],
            store_id=s['id'],
            amount=100.0,
            method='cash',
            status='pending',
        )
        db.session.add(p)
        db.session.commit()
        payment_id = p.id

    _login(client, login, admin)
    r = client.post(f'/admin/payments/{payment_id}/status', data={'new_status': 'paid'})
    assert r.status_code == 302
    with app.app_context():
        p = db.session.get(Payment, payment_id)
        assert p.status == 'paid'


def test_admin_update_payment_status_rejects_invalid(
    client, app, make_user, make_store, login
):
    admin = make_user(username='a_pay3', role='admin')
    s = make_store()
    with app.app_context():
        p = Payment(
            user_id=admin['id'],
            store_id=s['id'],
            amount=100.0,
            method='cash',
            status='pending',
        )
        db.session.add(p)
        db.session.commit()
        payment_id = p.id

    _login(client, login, admin)
    r = client.post(
        f'/admin/payments/{payment_id}/status',
        data={'new_status': 'invalid_status'}
    )
    assert r.status_code == 302
    with app.app_context():
        p = db.session.get(Payment, payment_id)
        assert p.status == 'pending'
