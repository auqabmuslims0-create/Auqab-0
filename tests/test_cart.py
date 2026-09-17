"""
اختبارات السلة.

ملاحظة تصميمية مهمة:
  السلة مقصورة على المستخدمين المسجّلين.
  الزوار غير المسجّلين يُحوَّلون إلى /login قبل الوصول لأي مسار سلة،
  لأن صاحب المتجر والمندوب يحتاجان بيانات العميل (هاتف/عنوان) لإتمام الطلب.

  الاستثناء الوحيد: /api/cart/sync — مساره يبدأ بـ /api/ فيُعفى من الحماية
  (لأغراض مزامنة localStorage من التطبيقات المحمولة قبل تسجيل الدخول).
"""
from database import db
from models import CartItem, Product


def _login(client, login_fixture, u):
    r = login_fixture(u['username'], u['password'])
    assert r.status_code == 302


# ═══════════════════════════════════════════════════════════════
# حماية السلة — الزوار يُحوَّلون إلى login
# ═══════════════════════════════════════════════════════════════
def test_anonymous_redirected_from_cart(client):
    r = client.get('/cart')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_anonymous_cannot_add_to_cart(client, make_active_store, make_product):
    s = make_active_store()
    p = make_product(s['id'], stock=10)
    r = client.post(f'/cart/add/{p["id"]}', data={'quantity': '1'})
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_anonymous_redirected_from_cart_count(client):
    r = client.get('/cart/count')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_anonymous_cannot_update_cart(client, make_active_store, make_product):
    s = make_active_store()
    p = make_product(s['id'], stock=10)
    r = client.post(f'/cart/update/{p["id"]}', data={'quantity': '5'})
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_anonymous_cannot_clear_cart(client):
    r = client.post('/cart/clear')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


# ═══════════════════════════════════════════════════════════════
# إضافة للسلة (مسجّل)
# ═══════════════════════════════════════════════════════════════
def test_add_to_cart_persists_to_db(
    client, app, make_user, login, make_active_store, make_product
):
    u = make_user(username='buyer1')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'], stock=10)
    r = client.post(f'/cart/add/{p["id"]}', data={'quantity': '2'})
    assert r.status_code == 302
    with app.app_context():
        item = CartItem.query.filter_by(
            user_id=u['id'], product_id=p['id']
        ).first()
        assert item is not None
        assert item.quantity == 2


def test_add_to_cart_rejects_when_exceeds_stock(
    client, app, make_user, login, make_active_store, make_product
):
    """لا يُضاف أي عنصر للسلة إذا تجاوز الطلب المخزون المتاح."""
    u = make_user(username='buyer2')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'], stock=2)
    r = client.post(f'/cart/add/{p["id"]}', data={'quantity': '5'})
    assert r.status_code == 302
    with app.app_context():
        item = CartItem.query.filter_by(
            user_id=u['id'], product_id=p['id']
        ).first()
        assert item is None


def test_add_to_cart_multiple_times_accumulates(
    client, app, make_user, login, make_active_store, make_product
):
    u = make_user(username='buyer3')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'], stock=10)
    client.post(f'/cart/add/{p["id"]}', data={'quantity': '2'})
    client.post(f'/cart/add/{p["id"]}', data={'quantity': '3'})
    with app.app_context():
        item = CartItem.query.filter_by(
            user_id=u['id'], product_id=p['id']
        ).first()
        assert item.quantity == 5


# ═══════════════════════════════════════════════════════════════
# AJAX responses
# ═══════════════════════════════════════════════════════════════
def test_add_to_cart_ajax_returns_json(
    client, make_user, login, make_active_store, make_product
):
    u = make_user(username='buyer4')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'], stock=10)
    r = client.post(
        f'/cart/add/{p["id"]}',
        data={'quantity': '2'},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data['status'] == 'success'
    assert data['cart_count'] == 2


def test_add_to_cart_ajax_insufficient_stock(
    client, make_user, login, make_active_store, make_product
):
    u = make_user(username='buyer5')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'], stock=1)
    r = client.post(
        f'/cart/add/{p["id"]}',
        data={'quantity': '100'},
        headers={'X-Requested-With': 'XMLHttpRequest'},
    )
    assert r.status_code == 400
    assert r.get_json()['status'] == 'error'


# ═══════════════════════════════════════════════════════════════
# التحديث / الإزالة / المسح
# ═══════════════════════════════════════════════════════════════
def test_update_cart_quantity(
    client, app, make_user, login, make_active_store, make_product
):
    u = make_user(username='buyer6')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'], stock=10)
    client.post(f'/cart/add/{p["id"]}', data={'quantity': '2'})
    client.post(f'/cart/update/{p["id"]}', data={'quantity': '5'})
    with app.app_context():
        item = CartItem.query.filter_by(
            user_id=u['id'], product_id=p['id']
        ).first()
        assert item.quantity == 5


def test_update_cart_clamps_to_stock(
    client, app, make_user, login, make_active_store, make_product
):
    u = make_user(username='buyer7')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'], stock=3)
    client.post(f'/cart/add/{p["id"]}', data={'quantity': '2'})
    client.post(f'/cart/update/{p["id"]}', data={'quantity': '100'})
    with app.app_context():
        item = CartItem.query.filter_by(
            user_id=u['id'], product_id=p['id']
        ).first()
        assert item.quantity == 3


def test_update_cart_action_remove(
    client, app, make_user, login, make_active_store, make_product
):
    u = make_user(username='buyer8')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'], stock=10)
    client.post(f'/cart/add/{p["id"]}', data={'quantity': '2'})
    client.post(f'/cart/update/{p["id"]}', data={'action': 'remove'})
    with app.app_context():
        item = CartItem.query.filter_by(
            user_id=u['id'], product_id=p['id']
        ).first()
        assert item is None


def test_remove_from_cart(
    client, app, make_user, login, make_active_store, make_product
):
    u = make_user(username='buyer9')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'], stock=10)
    client.post(f'/cart/add/{p["id"]}', data={'quantity': '2'})
    client.post(f'/cart/remove/{p["id"]}')
    with app.app_context():
        item = CartItem.query.filter_by(
            user_id=u['id'], product_id=p['id']
        ).first()
        assert item is None


def test_clear_cart(
    client, app, make_user, login, make_active_store, make_product
):
    u = make_user(username='buyer10')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'], stock=10)
    client.post(f'/cart/add/{p["id"]}', data={'quantity': '2'})
    client.post('/cart/clear')
    with app.app_context():
        count = CartItem.query.filter_by(user_id=u['id']).count()
        assert count == 0


def test_clear_store_cart(
    client, app, make_user, login, make_active_store, make_product
):
    u = make_user(username='buyer11')
    _login(client, login, u)
    s1 = make_active_store(name='S1')
    s2 = make_active_store(name='S2')
    p1 = make_product(s1['id'], stock=10)
    p2 = make_product(s2['id'], stock=10)
    client.post(f'/cart/add/{p1["id"]}', data={'quantity': '1'})
    client.post(f'/cart/add/{p2["id"]}', data={'quantity': '1'})
    client.post(f'/cart/clear/{s1["id"]}')
    with app.app_context():
        items = CartItem.query.filter_by(user_id=u['id']).all()
        product_ids = {it.product_id for it in items}
        assert p1['id'] not in product_ids
        assert p2['id'] in product_ids


# ═══════════════════════════════════════════════════════════════
# المزامنة من العميل
# ═══════════════════════════════════════════════════════════════
def test_sync_cart_anonymous_works_via_api_prefix(
    client, make_active_store, make_product
):
    """
    /api/cart/sync مسار خاص: يبدأ بـ /api/ فيُعفى من حماية login
    في before_request_checks. هذا مقصود — للسماح للتطبيقات المحمولة
    بمزامنة localStorage قبل تسجيل الدخول.
    """
    s = make_active_store()
    p = make_product(s['id'], stock=10)
    r = client.post('/api/cart/sync', json={
        'cart': {str(p['id']): 3}
    })
    assert r.status_code == 200
    assert r.get_json()['status'] == 'success'


def test_sync_cart_authenticated_replaces_db(
    client, app, make_user, login, make_active_store, make_product
):
    u = make_user(username='buyer12')
    _login(client, login, u)
    s = make_active_store()
    p1 = make_product(s['id'], stock=10)
    p2 = make_product(s['id'], stock=10)
    client.post(f'/cart/add/{p1["id"]}', data={'quantity': '2'})
    r = client.post('/api/cart/sync', json={
        'cart': {str(p2['id']): 4}
    })
    assert r.status_code == 200
    with app.app_context():
        items = CartItem.query.filter_by(user_id=u['id']).all()
        product_ids = {it.product_id for it in items}
        assert p1['id'] not in product_ids
        assert p2['id'] in product_ids


def test_sync_cart_rejects_invalid_payload(client):
    r = client.post('/api/cart/sync', json={'cart': 'not-a-dict'})
    assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# cart_count endpoint
# ═══════════════════════════════════════════════════════════════
def test_cart_count_endpoint(
    client, make_user, login, make_active_store, make_product
):
    u = make_user(username='buyer13')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'], stock=10)
    client.post(f'/cart/add/{p["id"]}', data={'quantity': '4'})
    r = client.get('/cart/count')
    assert r.status_code == 200
    assert r.get_json()['cart_count'] == 4


# ═══════════════════════════════════════════════════════════════
# دمج سلة الزائر مع DB عند login/register
# ═══════════════════════════════════════════════════════════════
def test_login_merges_anonymous_session_cart_to_db(
    client, app, make_user, make_active_store, make_product
):
    """
    سلة الزائر (من /api/cart/sync) تُدمَج مع DB عند تسجيل الدخول.
    Regression test: قبل الإصلاح، الدمج كان يحدث فقط عند زيارة /cart،
    فلا يظهر cart_count في /api/updates ولا في صفحات أخرى.
    """
    u = make_user(username='mergeowner', password='MergePass123!@#')
    s = make_active_store(has_delivery=False)
    p = make_product(s['id'], stock=10)

    # 1) زائر يزامن سلة من localStorage
    r = client.post('/api/cart/sync', json={'cart': {str(p['id']): 3}})
    assert r.status_code == 200
    with client.session_transaction() as sess:
        assert sess['cart'][str(p['id'])] == 3

    # 2) يسجّل الدخول
    r = client.post('/login', data={
        'login_id': u['username'],
        'password': u['password'],
    })
    assert r.status_code == 302

    # 3) السلة موجودة الآن في DB (بدون زيارة /cart)
    with app.app_context():
        item = CartItem.query.filter_by(
            user_id=u['id'], product_id=p['id']
        ).first()
        assert item is not None
        assert item.quantity == 3


def test_register_merges_anonymous_session_cart_to_db(
    client, app, make_active_store, make_product
):
    """
    سلة الزائر تُدمَج مع DB عند إنشاء حساب جديد (3 خطوات).
    """
    s = make_active_store(has_delivery=False)
    p = make_product(s['id'], stock=10)

    # 1) زائر يزامن سلة
    r = client.post('/api/cart/sync', json={'cart': {str(p['id']): 2}})
    assert r.status_code == 200

    # 2) تسجيل كامل عبر 3 خطوات
    client.post('/register?step=1', data={
        'step': '1', 'username': 'newmerge',
        'email': 'newmerge@test.local', 'phone': '977000111',
    })
    client.post('/register?step=2', data={
        'step': '2',
        'password': 'NewMerge123!@#',
        'confirm_password': 'NewMerge123!@#',
        'role': 'customer',
        'agree': 'on',
    })
    r = client.post('/register?step=3', data={'step': '3', 'bio': ''})
    assert r.status_code == 302

    # 3) السلة في DB
    with app.app_context():
        from models import User
        new_user = User.query.filter_by(username='newmerge').first()
        assert new_user is not None
        item = CartItem.query.filter_by(
            user_id=new_user.id, product_id=p['id']
        ).first()
        assert item is not None
        assert item.quantity == 2
