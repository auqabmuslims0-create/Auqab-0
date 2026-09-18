"""
اختبارات طبقة صاحب المتجر (store_owner).

تغطي:
- RBAC على كل مسارات المتجر × 4 أدوار
- عزل الملكية: owner A لا يصل لمتجر B (يجب 404 لا 403)
- إدارة المنتجات (CRUD مبسط — بدون ملفات)
- إدارة التصنيفات (CRUD + هرمية + تعيين المنتجات)
- إدارة الطلبات (transition rules + assign delivery)
- الاشتراك (submit → pending → confirm)
- إعدادات المتجر (edit, request_delete, cancel_delete)
- الإحصاءات
"""
from datetime import timedelta
import pytest
from database import db
from models import (
    User, Store, Product, Category, Order, OrderItem,
    Subscription, Payment, Reel,
)
from shared.time_utils import current_time
from shared.services.order_service import OrderService


def _login(client, login_fixture, u):
    assert login_fixture(u['username'], u['password']).status_code == 302


# ═══════════════════════════════════════════════════════════════
# RBAC على مسارات المتجر
# ═══════════════════════════════════════════════════════════════
STORE_PATHS_TEMPLATE = [
    '/store/{sid}',
    '/store/{sid}/products',
    '/store/{sid}/products/new',
    '/store/{sid}/categories',
    '/store/{sid}/orders',
    '/store/{sid}/subscription',
    '/store/{sid}/edit',
    '/store/{sid}/reels',
]

NO_SID_PATHS = ['/my_stores', '/store/new', '/store/stats']


@pytest.mark.parametrize('tmpl', STORE_PATHS_TEMPLATE)
def test_store_paths_reject_customer(client, make_user, make_active_store, login, tmpl):
    s = make_active_store()
    u = make_user(username=f'cust_{tmpl[:15]}', role='customer')
    _login(client, login, u)
    r = client.get(tmpl.format(sid=s['id']))
    assert r.status_code == 403


@pytest.mark.parametrize('tmpl', STORE_PATHS_TEMPLATE)
def test_store_paths_reject_admin(client, make_user, make_active_store, login, tmpl):
    """admin أيضاً لا يمر من @role_required('owner')."""
    s = make_active_store()
    u = make_user(username=f'adm_{tmpl[:15]}', role='admin')
    _login(client, login, u)
    r = client.get(tmpl.format(sid=s['id']))
    assert r.status_code == 403


@pytest.mark.parametrize('path', NO_SID_PATHS)
def test_store_paths_reject_customer_no_sid(client, make_user, login, path):
    u = make_user(username=f'cust_p_{path[1:10]}', role='customer')
    _login(client, login, u)
    r = client.get(path)
    assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════
# عزل الملكية — owner A لا يصل لمتجر B (404 للتفادي User Enumeration)
# ═══════════════════════════════════════════════════════════════
def test_owner_a_cannot_access_owner_b_store(client, make_user, make_active_store, login):
    owner_a = make_user(username='ownerA_iso', role='owner')
    owner_b = make_user(username='ownerB_iso', role='owner')
    store_b = make_active_store(owner_id=owner_b['id'], name='BStore')

    _login(client, login, owner_a)
    r = client.get(f'/store/{store_b["id"]}')
    assert r.status_code == 404


def test_owner_a_cannot_edit_owner_b_product(
    client, make_user, make_active_store, make_product, login
):
    owner_a = make_user(username='ownerA_iso2', role='owner')
    owner_b = make_user(username='ownerB_iso2', role='owner')
    store_b = make_active_store(owner_id=owner_b['id'])
    p = make_product(store_b['id'])

    _login(client, login, owner_a)
    r = client.get(f'/store/{store_b["id"]}/products/{p["id"]}/edit')
    assert r.status_code == 404


def test_owner_a_cannot_delete_owner_b_category(
    client, app, make_user, make_active_store, login
):
    owner_a = make_user(username='ownerA_iso3', role='owner')
    owner_b = make_user(username='ownerB_iso3', role='owner')
    store_b = make_active_store(owner_id=owner_b['id'])

    with app.app_context():
        cat = Category(name='BCat', store_id=store_b['id'])
        db.session.add(cat)
        db.session.commit()
        cat_id = cat.id

    _login(client, login, owner_a)
    r = client.post(f'/store/{store_b["id"]}/categories/{cat_id}/delete')
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# إدارة المنتجات
# ═══════════════════════════════════════════════════════════════
def test_new_product_minimal(client, app, make_user, make_active_store, login):
    owner = make_user(username='p_owner1', role='owner')
    s = make_active_store(owner_id=owner['id'])
    _login(client, login, owner)

    r = client.post(f'/store/{s["id"]}/products/new', data={
        'name': 'TestProduct',
        'description': 'desc',
        'price': '150',
        'stock_quantity': '10',
        'category_id': '',
        'options': '',
    })
    assert r.status_code == 302
    with app.app_context():
        p = Product.query.filter_by(name='TestProduct').first()
        assert p is not None
        assert p.price == 150.0
        assert p.stock_quantity == 10


def test_new_product_rejects_missing_name(client, make_user, make_active_store, login):
    owner = make_user(username='p_owner2', role='owner')
    s = make_active_store(owner_id=owner['id'])
    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/products/new', data={
        'name': '',
        'price': '100',
    })
    assert r.status_code == 302


def test_new_product_rejects_negative_price(client, app, make_user, make_active_store, login):
    owner = make_user(username='p_owner3', role='owner')
    s = make_active_store(owner_id=owner['id'])
    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/products/new', data={
        'name': 'NegPrice',
        'price': '-5',
        'stock_quantity': '10',
    })
    assert r.status_code == 302
    with app.app_context():
        assert Product.query.filter_by(name='NegPrice').first() is None


def test_new_product_hidden_price(client, app, make_user, make_active_store, login):
    owner = make_user(username='p_owner4', role='owner')
    s = make_active_store(owner_id=owner['id'])
    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/products/new', data={
        'name': 'HiddenPrice',
        'price': '',
        'stock_quantity': '5',
        'hide_price': 'yes',
    })
    assert r.status_code == 302
    with app.app_context():
        p = Product.query.filter_by(name='HiddenPrice').first()
        assert p is not None
        assert p.hide_price is True
        assert p.price == 0.0


def test_edit_product(client, app, make_user, make_active_store, make_product, login):
    owner = make_user(username='p_owner5', role='owner')
    s = make_active_store(owner_id=owner['id'])
    p = make_product(s['id'], price=100, stock=10)
    _login(client, login, owner)

    r = client.post(f'/store/{s["id"]}/products/{p["id"]}/edit', data={
        'name': 'UpdatedName',
        'price': '250',
        'stock_quantity': '7',
        'category_id': '',
        'options': '',
    })
    assert r.status_code == 302
    with app.app_context():
        prod = db.session.get(Product, p['id'])
        assert prod.name == 'UpdatedName'
        assert prod.price == 250.0
        assert prod.stock_quantity == 7


def test_delete_product(client, app, make_user, make_active_store, make_product, login):
    owner = make_user(username='p_owner6', role='owner')
    s = make_active_store(owner_id=owner['id'])
    p = make_product(s['id'])
    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/products/{p["id"]}/delete')
    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(Product, p['id']) is None


def test_owner_cannot_create_product_in_inactive_store(
    client, make_user, make_store, login
):
    """متجر بلا اشتراك ساري → لا يمكن إضافة منتج."""
    owner = make_user(username='p_owner7', role='owner')
    s = make_store(owner_id=owner['id'], subscription_status='suspended')
    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/products/new', data={
        'name': 'ShouldFail',
        'price': '100',
    })
    # يُعيد توجيه بدل تنفيذ العملية
    assert r.status_code == 302


# ═══════════════════════════════════════════════════════════════
# إدارة التصنيفات
# ═══════════════════════════════════════════════════════════════
def test_new_category(client, app, make_user, make_active_store, login):
    owner = make_user(username='c_owner1', role='owner')
    s = make_active_store(owner_id=owner['id'])
    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/categories/new', data={'name': 'CategoryA'})
    assert r.status_code == 302
    with app.app_context():
        c = Category.query.filter_by(name='CategoryA', store_id=s['id']).first()
        assert c is not None


def test_new_category_with_parent(client, app, make_user, make_active_store, login):
    owner = make_user(username='c_owner2', role='owner')
    s = make_active_store(owner_id=owner['id'])
    with app.app_context():
        parent = Category(name='Parent', store_id=s['id'])
        db.session.add(parent)
        db.session.commit()
        parent_id = parent.id

    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/categories/new', data={
        'name': 'Child', 'parent_id': str(parent_id)
    })
    assert r.status_code == 302
    with app.app_context():
        c = Category.query.filter_by(name='Child').first()
        assert c.parent_id == parent_id


def test_delete_category_rejects_with_products(
    client, app, make_user, make_active_store, make_product, login
):
    owner = make_user(username='c_owner3', role='owner')
    s = make_active_store(owner_id=owner['id'])
    with app.app_context():
        c = Category(name='WithProducts', store_id=s['id'])
        db.session.add(c)
        db.session.commit()
        cat_id = c.id
    p = make_product(s['id'])
    with app.app_context():
        prod = db.session.get(Product, p['id'])
        prod.category_id = cat_id
        db.session.commit()

    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/categories/{cat_id}/delete')
    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(Category, cat_id) is not None


def test_delete_category_rejects_with_children(
    client, app, make_user, make_active_store, login
):
    owner = make_user(username='c_owner4', role='owner')
    s = make_active_store(owner_id=owner['id'])
    with app.app_context():
        parent = Category(name='ParentC', store_id=s['id'])
        db.session.add(parent)
        db.session.commit()
        parent_id = parent.id
        child = Category(name='ChildC', store_id=s['id'], parent_id=parent_id)
        db.session.add(child)
        db.session.commit()

    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/categories/{parent_id}/delete')
    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(Category, parent_id) is not None


def test_delete_empty_category(client, app, make_user, make_active_store, login):
    owner = make_user(username='c_owner5', role='owner')
    s = make_active_store(owner_id=owner['id'])
    with app.app_context():
        c = Category(name='EmptyC', store_id=s['id'])
        db.session.add(c)
        db.session.commit()
        cat_id = c.id

    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/categories/{cat_id}/delete')
    assert r.status_code == 302
    with app.app_context():
        assert db.session.get(Category, cat_id) is None


def test_manage_category_products_assigns(
    client, app, make_user, make_active_store, make_product, login
):
    owner = make_user(username='c_owner6', role='owner')
    s = make_active_store(owner_id=owner['id'])
    with app.app_context():
        c = Category(name='AssignC', store_id=s['id'])
        db.session.add(c)
        db.session.commit()
        cat_id = c.id
    p = make_product(s['id'])

    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/categories/{cat_id}/manage-products', data={
        'product_ids': [str(p['id'])]
    })
    assert r.status_code == 302
    with app.app_context():
        prod = db.session.get(Product, p['id'])
        assert prod.category_id == cat_id


# ═══════════════════════════════════════════════════════════════
# إدارة الطلبات
# ═══════════════════════════════════════════════════════════════
def _make_order_for_store(app, store_id, customer_id):
    """
    إنشاء طلب اختباري.
    نُمرِّر دائماً delivery_address + إحداثيات — تُتجاهل عندما
    has_delivery=False، وتُستخدم عندما True. هذا يوحّد المسار.
    """
    with app.app_context():
        user = db.session.get(User, customer_id)
        store = db.session.get(Store, store_id)
        from models import Product
        product = Product.query.filter_by(store_id=store.id).first()
        if not product:
            product = Product(store_id=store.id, name='OProduct', price=50.0, stock_quantity=10)
            db.session.add(product)
            db.session.commit()
        order = OrderService.create_order(
            user=user, store=store,
            cart_items=[{'product': product, 'quantity': 1}],
            delivery_address='Test Address, Damascus',
            latitude=33.5,
            longitude=36.3,
        )
        return order.id


def test_store_orders_list(client, app, make_user, make_active_store, login):
    owner = make_user(username='o_owner1', role='owner')
    s = make_active_store(owner_id=owner['id'])
    customer = make_user(username='o_cust1')
    _make_order_for_store(app, s['id'], customer['id'])

    _login(client, login, owner)
    r = client.get(f'/store/{s["id"]}/orders')
    assert r.status_code == 200


def test_update_order_status_accepts_confirmed(
    client, app, make_user, make_active_store, login
):
    owner = make_user(username='o_owner2', role='owner')
    s = make_active_store(owner_id=owner['id'])
    customer = make_user(username='o_cust2')
    order_id = _make_order_for_store(app, s['id'], customer['id'])

    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/orders/{order_id}/status', data={'status': 'confirmed'})
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.status == 'confirmed'


def test_update_order_status_rejects_delivering(
    client, app, make_user, make_active_store, login
):
    """صاحب المتجر لا يستطيع وضع 'delivering' — من صلاحية المندوب."""
    owner = make_user(username='o_owner3', role='owner')
    s = make_active_store(owner_id=owner['id'])
    customer = make_user(username='o_cust3')
    order_id = _make_order_for_store(app, s['id'], customer['id'])

    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/orders/{order_id}/status', data={'status': 'delivering'})
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.status == 'new'


def test_update_order_status_rejects_delivered(
    client, app, make_user, make_active_store, login
):
    owner = make_user(username='o_owner4', role='owner')
    s = make_active_store(owner_id=owner['id'])
    customer = make_user(username='o_cust4')
    order_id = _make_order_for_store(app, s['id'], customer['id'])

    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/orders/{order_id}/status', data={'status': 'delivered'})
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.status == 'new'


# ═══════════════════════════════════════════════════════════════
# إسناد مندوب
# ═══════════════════════════════════════════════════════════════
def test_assign_delivery_requires_ready_status(
    client, app, make_user, make_active_store, login
):
    owner = make_user(username='ad_owner1', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='ad_cust1')
    driver = make_user(username='ad_driver1', role='delivery')
    order_id = _make_order_for_store(app, s['id'], customer['id'])

    # الطلب في حالة 'new' — لا يمكن الإسناد
    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/orders/{order_id}/assign-delivery', data={
        'delivery_person_id': str(driver['id'])
    })
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.delivery_person_id is None


def test_assign_delivery_success(client, app, make_user, make_active_store, login):
    owner = make_user(username='ad_owner2', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='ad_cust2')
    driver = make_user(username='ad_driver2', role='delivery', phone='+963911111199')
    order_id = _make_order_for_store(app, s['id'], customer['id'])

    # Prepare: new → confirmed → preparing → ready
    with app.app_context():
        o = db.session.get(Order, order_id)
        for st in ['confirmed', 'preparing', 'ready']:
            o.status = st
        db.session.commit()

    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/orders/{order_id}/assign-delivery', data={
        'delivery_person_id': str(driver['id'])
    })
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.delivery_person_id == driver['id']
        assert o.pickup_code is not None


def test_assign_delivery_rejects_when_no_delivery_service(
    client, app, make_user, make_active_store, login
):
    owner = make_user(username='ad_owner3', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=False)
    customer = make_user(username='ad_cust3')
    driver = make_user(username='ad_driver3', role='delivery')
    order_id = _make_order_for_store(app, s['id'], customer['id'])

    with app.app_context():
        o = db.session.get(Order, order_id)
        o.status = 'ready'
        db.session.commit()

    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/orders/{order_id}/assign-delivery', data={
        'delivery_person_id': str(driver['id'])
    })
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.delivery_person_id is None


def test_assign_delivery_rejects_inactive_driver(
    client, app, make_user, make_active_store, login
):
    owner = make_user(username='ad_owner4', role='owner')
    s = make_active_store(owner_id=owner['id'], has_delivery=True)
    customer = make_user(username='ad_cust4')
    driver = make_user(username='ad_driver4', role='delivery', is_active=False)
    order_id = _make_order_for_store(app, s['id'], customer['id'])

    with app.app_context():
        o = db.session.get(Order, order_id)
        o.status = 'ready'
        db.session.commit()

    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/orders/{order_id}/assign-delivery', data={
        'delivery_person_id': str(driver['id'])
    })
    assert r.status_code == 302
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.delivery_person_id is None


# ═══════════════════════════════════════════════════════════════
# الاشتراك
# ═══════════════════════════════════════════════════════════════
def test_subscription_submit_creates_pending(
    client, app, make_user, make_store, login
):
    owner = make_user(username='s_owner1', role='owner')
    s = make_store(owner_id=owner['id'], subscription_status='pending')
    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/subscription/method/manual_delivery')
    assert r.status_code == 302
    with app.app_context():
        sub = Subscription.query.filter_by(store_id=s['id'], status='pending').first()
        assert sub is not None


def test_subscription_confirm_success(
    client, app, make_user, make_store, login
):
    from shared.services.subscription_service import SubscriptionService
    owner = make_user(username='s_owner2', role='owner')
    s = make_store(owner_id=owner['id'], subscription_status='pending')

    with app.app_context():
        user = db.session.get(User, owner['id'])
        store = db.session.get(Store, s['id'])
        _, _, sub = SubscriptionService.submit_subscription_request(
            user, store, payment_method='manual_delivery'
        )
        sub_id = sub.id
        code = sub.confirmation_code

    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/subscription/confirm', data={
        'confirmation_code': code
    })
    assert r.status_code == 302
    with app.app_context():
        sub = db.session.get(Subscription, sub_id)
        assert sub.status == 'paid'


# ═══════════════════════════════════════════════════════════════
# إعدادات المتجر
# ═══════════════════════════════════════════════════════════════
def test_edit_store(client, app, make_user, make_active_store, login):
    owner = make_user(username='e_owner1', role='owner')
    s = make_active_store(owner_id=owner['id'])
    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/edit', data={
        'name': 'UpdatedStoreName',
        'description': 'new desc',
        'address': 'new address',
        'phone': '',
        'opening_time': '09:00',
        'closing_time': '18:00',
        'has_delivery': 'yes',
    })
    assert r.status_code == 302
    with app.app_context():
        store = db.session.get(Store, s['id'])
        assert store.name == 'UpdatedStoreName'
        assert store.has_delivery is True
        assert store.working_hours == '09:00 - 18:00'


def test_edit_store_rejects_empty_name(client, app, make_user, make_active_store, login):
    owner = make_user(username='e_owner2', role='owner')
    s = make_active_store(owner_id=owner['id'])
    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/edit', data={
        'name': '',
    })
    assert r.status_code == 302
    with app.app_context():
        store = db.session.get(Store, s['id'])
        # الاسم الأصلي لم يتغير
        assert store.name != ''


def test_request_delete_schedules(client, app, make_user, make_active_store, login):
    owner = make_user(username='e_owner3', role='owner')
    s = make_active_store(owner_id=owner['id'])
    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/request_delete')
    assert r.status_code == 302
    with app.app_context():
        store = db.session.get(Store, s['id'])
        assert store.pending_deletion_at is not None


def test_cancel_delete_clears_schedule(client, app, make_user, make_active_store, login):
    owner = make_user(username='e_owner4', role='owner')
    s = make_active_store(owner_id=owner['id'])
    with app.app_context():
        store = db.session.get(Store, s['id'])
        store.pending_deletion_at = current_time() + timedelta(hours=24)
        db.session.commit()

    _login(client, login, owner)
    r = client.post(f'/store/{s["id"]}/cancel_delete')
    assert r.status_code == 302
    with app.app_context():
        store = db.session.get(Store, s['id'])
        assert store.pending_deletion_at is None


# ═══════════════════════════════════════════════════════════════
# الإحصاءات
# ═══════════════════════════════════════════════════════════════
def test_store_stats_requires_store(client, make_user, login):
    owner = make_user(username='st_owner1', role='owner')
    _login(client, login, owner)
    r = client.get('/store/stats', follow_redirects=False)
    # يوجّه لـ my_stores لأن المستخدم بلا متاجر
    assert r.status_code == 302
    assert 'my_stores' in r.headers['Location']


def test_store_stats_accessible_with_store(
    client, make_user, make_active_store, login
):
    owner = make_user(username='st_owner2', role='owner')
    make_active_store(owner_id=owner['id'])
    _login(client, login, owner)
    r = client.get('/store/stats')
    assert r.status_code == 200


def test_store_stats_filter_by_store(
    client, make_user, make_active_store, login
):
    owner = make_user(username='st_owner3', role='owner')
    s = make_active_store(owner_id=owner['id'])
    _login(client, login, owner)
    r = client.get(f'/store/stats?store_id={s["id"]}')
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════
# قائمة المتاجر
# ═══════════════════════════════════════════════════════════════
def test_my_stores_lists_owner_stores(client, make_user, make_active_store, login):
    owner = make_user(username='m_owner1', role='owner')
    make_active_store(owner_id=owner['id'], name='MyStoreOne')
    _login(client, login, owner)
    r = client.get('/my_stores')
    assert r.status_code == 200
    assert b'MyStoreOne' in r.data
