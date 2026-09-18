"""
اختبارات blueprints/api/* — JWT Bearer endpoints.

هذه الواجهات يستخدمها تطبيق الجوال المستقبلي.
- المصادقة عبر Authorization: Bearer <token>
- CSRF معفى (api_bp في قائمة exempt) — لا تعتمد على كوكي
"""
import pytest
from database import db
from models import User, Store, Product, Order, Favorite


def _jwt_token(app, user_id):
    with app.app_context():
        from blueprints.api.helpers import encode_auth_token
        return encode_auth_token(user_id)


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


# ═══════════════════════════════════════════════════════════════
# POST /api/register
# ═══════════════════════════════════════════════════════════════
def test_register_success(client):
    r = client.post('/api/register', json={
        'username': 'api_reg1',
        'email': 'api_reg1@test.local',
        'phone': '912345678',
        'password': 'StrongPass123!@#',
        'role': 'customer',
    })
    assert r.status_code == 201
    data = r.get_json()
    assert 'token' in data
    assert data['user']['username'] == 'api_reg1'


def test_register_rejects_weak_password(client):
    r = client.post('/api/register', json={
        'username': 'api_weak',
        'email': 'api_weak@test.local',
        'password': '123',
    })
    assert r.status_code == 400


def test_register_rejects_duplicate_username(client, make_user):
    make_user(username='api_dup', email='api_dup@test.local')
    r = client.post('/api/register', json={
        'username': 'api_dup',
        'email': 'api_other@test.local',
        'password': 'StrongPass123!@#',
    })
    assert r.status_code == 400


def test_register_rejects_duplicate_email(client, make_user):
    make_user(username='api_dup2', email='api_dup2@test.local')
    r = client.post('/api/register', json={
        'username': 'api_unique',
        'email': 'api_dup2@test.local',
        'password': 'StrongPass123!@#',
    })
    assert r.status_code == 400


def test_register_rejects_missing_fields(client):
    r = client.post('/api/register', json={'username': 'only_name'})
    assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# POST /api/login
# ═══════════════════════════════════════════════════════════════
def test_login_success_with_username(client, make_user):
    u = make_user(username='api_log1', password='MyPass123!@#')
    r = client.post('/api/login', json={
        'login_id': 'api_log1',
        'password': 'MyPass123!@#',
    })
    assert r.status_code == 200
    assert 'token' in r.get_json()


def test_login_success_with_email(client, make_user):
    u = make_user(username='api_log2', password='MyPass123!@#',
                  email='api_log2@test.local')
    r = client.post('/api/login', json={
        'login_id': 'api_log2@test.local',
        'password': 'MyPass123!@#',
    })
    assert r.status_code == 200


def test_login_wrong_password(client, make_user):
    make_user(username='api_log3', password='MyPass123!@#')
    r = client.post('/api/login', json={
        'login_id': 'api_log3',
        'password': 'WrongPass123!@#',
    })
    assert r.status_code == 401


def test_login_inactive_user(client, make_user):
    make_user(username='api_log4', password='MyPass123!@#', is_active=False)
    r = client.post('/api/login', json={
        'login_id': 'api_log4',
        'password': 'MyPass123!@#',
    })
    assert r.status_code == 403


# ═══════════════════════════════════════════════════════════════
# GET/PUT /api/me
# ═══════════════════════════════════════════════════════════════
def test_me_requires_token(client):
    r = client.get('/api/me')
    assert r.status_code == 401


def test_me_invalid_token(client):
    r = client.get('/api/me', headers={'Authorization': 'Bearer garbage'})
    assert r.status_code == 401


def test_me_success(client, app, make_user):
    u = make_user(username='api_me1')
    token = _jwt_token(app, u['id'])
    r = client.get('/api/me', headers=_auth(token))
    assert r.status_code == 200
    assert r.get_json()['user']['username'] == 'api_me1'


def test_update_me_success(client, app, make_user):
    u = make_user(username='api_me2', email='api_me2@test.local')
    token = _jwt_token(app, u['id'])
    r = client.put('/api/me', headers=_auth(token), json={
        'username': 'api_me2_updated',
        'email': 'api_me2_updated@test.local',
        'phone': '912000111',
    })
    assert r.status_code == 200
    with app.app_context():
        user = db.session.get(User, u['id'])
        assert user.username == 'api_me2_updated'
        assert user.phone == '+963912000111'


def test_update_me_rejects_duplicate_username(client, app, make_user):
    u1 = make_user(username='api_me3')
    u2 = make_user(username='api_me3_taken')
    token = _jwt_token(app, u1['id'])
    r = client.put('/api/me', headers=_auth(token), json={
        'username': 'api_me3_taken',
        'email': u1['email'],
    })
    assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# POST /api/me/change_password
# ═══════════════════════════════════════════════════════════════
def test_change_password_success(client, app, make_user):
    u = make_user(username='api_chp1', password='OldPass123!@#')
    token = _jwt_token(app, u['id'])
    r = client.post('/api/me/change_password', headers=_auth(token), json={
        'current_password': 'OldPass123!@#',
        'new_password': 'NewStrong456!@#',
        'confirm_password': 'NewStrong456!@#',
    })
    assert r.status_code == 200
    # Verify: يمكن الدخول بكلمة المرور الجديدة
    r = client.post('/api/login', json={
        'login_id': 'api_chp1', 'password': 'NewStrong456!@#',
    })
    assert r.status_code == 200


def test_change_password_wrong_current(client, app, make_user):
    u = make_user(username='api_chp2', password='OldPass123!@#')
    token = _jwt_token(app, u['id'])
    r = client.post('/api/me/change_password', headers=_auth(token), json={
        'current_password': 'WrongOld123!@#',
        'new_password': 'NewStrong456!@#',
        'confirm_password': 'NewStrong456!@#',
    })
    assert r.status_code == 400


def test_change_password_mismatch(client, app, make_user):
    u = make_user(username='api_chp3', password='OldPass123!@#')
    token = _jwt_token(app, u['id'])
    r = client.post('/api/me/change_password', headers=_auth(token), json={
        'current_password': 'OldPass123!@#',
        'new_password': 'NewStrong456!@#',
        'confirm_password': 'DifferentPass456!@#',
    })
    assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# POST /api/me/verify_password
# ═══════════════════════════════════════════════════════════════
def test_verify_password_valid(client, app, make_user):
    u = make_user(username='api_vp1', password='MyPass123!@#')
    token = _jwt_token(app, u['id'])
    r = client.post('/api/me/verify_password', headers=_auth(token),
                    json={'password': 'MyPass123!@#'})
    assert r.status_code == 200
    assert r.get_json()['valid'] is True


def test_verify_password_invalid(client, app, make_user):
    u = make_user(username='api_vp2', password='MyPass123!@#')
    token = _jwt_token(app, u['id'])
    r = client.post('/api/me/verify_password', headers=_auth(token),
                    json={'password': 'Wrong!@#'})
    assert r.status_code == 400
    assert r.get_json()['valid'] is False


# ═══════════════════════════════════════════════════════════════
# POST /api/me/delete
# ═══════════════════════════════════════════════════════════════
def test_delete_me_wrong_password(client, app, make_user):
    u = make_user(username='api_del1', password='MyPass123!@#')
    token = _jwt_token(app, u['id'])
    r = client.post('/api/me/delete', headers=_auth(token),
                    json={'password': 'Wrong!@#'})
    assert r.status_code == 403
    with app.app_context():
        assert db.session.get(User, u['id']) is not None


def test_delete_me_missing_password(client, app, make_user):
    u = make_user(username='api_del2', password='MyPass123!@#')
    token = _jwt_token(app, u['id'])
    r = client.post('/api/me/delete', headers=_auth(token), json={})
    assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# Favorites
# ═══════════════════════════════════════════════════════════════
def test_favorites_list_empty(client, app, make_user):
    u = make_user(username='api_fav1')
    token = _jwt_token(app, u['id'])
    r = client.get('/api/favorites', headers=_auth(token))
    assert r.status_code == 200
    assert r.get_json()['favorites'] == []


def test_favorite_toggle_product(client, app, make_user, make_active_store, make_product):
    u = make_user(username='api_fav2')
    s = make_active_store()
    p = make_product(s['id'])
    token = _jwt_token(app, u['id'])

    # Add
    r = client.post('/api/favorites/toggle', headers=_auth(token),
                    json={'type': 'product', 'id': p['id']})
    assert r.status_code == 200
    assert r.get_json()['is_favorite'] is True

    # Remove
    r = client.post('/api/favorites/toggle', headers=_auth(token),
                    json={'type': 'product', 'id': p['id']})
    assert r.status_code == 200
    assert r.get_json()['is_favorite'] is False


def test_favorite_toggle_invalid_type(client, app, make_user, make_active_store, make_product):
    u = make_user(username='api_fav3')
    s = make_active_store()
    p = make_product(s['id'])
    token = _jwt_token(app, u['id'])
    r = client.post('/api/favorites/toggle', headers=_auth(token),
                    json={'type': 'bogus', 'id': p['id']})
    assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# Public stores (no auth needed)
# ═══════════════════════════════════════════════════════════════
def test_stores_list_public(client, make_active_store):
    make_active_store(name='PublicStoreX')
    r = client.get('/api/stores')
    assert r.status_code == 200
    names = [s['name'] for s in r.get_json()['stores']]
    assert 'PublicStoreX' in names


def test_stores_get_hides_inactive(client, app, make_user, make_store):
    owner = make_user(username='api_own1', role='owner')
    inactive = make_store(owner_id=owner['id'], subscription_status='suspended')
    r = client.get(f'/api/stores/{inactive["id"]}')
    assert r.status_code == 404


def test_stores_mine_requires_jwt(client):
    r = client.get('/api/stores/mine')
    assert r.status_code == 401


def test_stores_mine_success(client, app, make_user, make_active_store):
    owner = make_user(username='api_own2', role='owner')
    make_active_store(owner_id=owner['id'], name='MineStore')
    token = _jwt_token(app, owner['id'])
    r = client.get('/api/stores/mine', headers=_auth(token))
    assert r.status_code == 200
    names = [s['name'] for s in r.get_json()['stores']]
    assert 'MineStore' in names


# ═══════════════════════════════════════════════════════════════
# Products
# ═══════════════════════════════════════════════════════════════
def test_get_product_public(client, make_active_store, make_product):
    s = make_active_store()
    p = make_product(s['id'], name='PublicProduct')
    r = client.get(f'/api/products/{p["id"]}')
    assert r.status_code == 200
    assert r.get_json()['product']['name'] == 'PublicProduct'


def test_search_products(client, make_active_store, make_product):
    s = make_active_store()
    make_product(s['id'], name='SearchableWidget')
    r = client.get('/api/search?q=SearchableWidget')
    assert r.status_code == 200
    names = [p['name'] for p in r.get_json()['products']]
    assert 'SearchableWidget' in names


# ═══════════════════════════════════════════════════════════════
# Orders (JWT)
# ═══════════════════════════════════════════════════════════════
def test_orders_create_requires_jwt(client):
    r = client.post('/api/orders', json={'items': [{'product_id': 1, 'quantity': 1}]})
    assert r.status_code == 401


def test_orders_create_success(client, app, make_user, make_active_store, make_product):
    u = make_user(username='api_ord1')
    s = make_active_store(has_delivery=False)
    p = make_product(s['id'], price=75.0, stock=10)
    token = _jwt_token(app, u['id'])

    r = client.post('/api/orders', headers=_auth(token), json={
        'items': [{'product_id': p['id'], 'quantity': 2}],
    })
    assert r.status_code == 201
    with app.app_context():
        assert Order.query.filter_by(customer_id=u['id']).count() == 1


def test_orders_list_own_only(client, app, make_user, make_active_store, make_product):
    u1 = make_user(username='api_ord_u1')
    u2 = make_user(username='api_ord_u2')
    s = make_active_store(has_delivery=False)
    p = make_product(s['id'], price=50.0, stock=20)

    # Order for u1
    token1 = _jwt_token(app, u1['id'])
    client.post('/api/orders', headers=_auth(token1), json={
        'items': [{'product_id': p['id'], 'quantity': 1}],
    })

    # Check u2 sees nothing
    token2 = _jwt_token(app, u2['id'])
    r = client.get('/api/orders', headers=_auth(token2))
    assert r.status_code == 200
    assert r.get_json()['orders'] == []


def test_orders_cancel_own(client, app, make_user, make_active_store, make_product):
    u = make_user(username='api_ord_can')
    s = make_active_store(has_delivery=False)
    p = make_product(s['id'], price=50.0, stock=10)
    token = _jwt_token(app, u['id'])

    r = client.post('/api/orders', headers=_auth(token), json={
        'items': [{'product_id': p['id'], 'quantity': 1}],
    })
    order_id = r.get_json()['order']['id']

    r = client.post(f'/api/orders/{order_id}/cancel', headers=_auth(token))
    assert r.status_code == 200
    with app.app_context():
        o = db.session.get(Order, order_id)
        assert o.status == 'cancelled'


def test_orders_get_other_user_403(client, app, make_user, make_active_store, make_product):
    u1 = make_user(username='api_ord_g1')
    u2 = make_user(username='api_ord_g2')
    s = make_active_store(has_delivery=False)
    p = make_product(s['id'], price=50.0, stock=10)

    token1 = _jwt_token(app, u1['id'])
    r = client.post('/api/orders', headers=_auth(token1), json={
        'items': [{'product_id': p['id'], 'quantity': 1}],
    })
    order_id = r.get_json()['order']['id']

    token2 = _jwt_token(app, u2['id'])
    r = client.get(f'/api/orders/{order_id}', headers=_auth(token2))
    assert r.status_code == 403
