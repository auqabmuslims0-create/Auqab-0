"""
اختبارات social_bp — التعليقات والتفاعلات على المنتجات.

سياسة CSRF: social_bp غير معفى (بعد إصلاح CSRF)، لكن conftest.py
يعطّل CSRF عالمياً. اختبار CSRF على هذه المسارات موجود في test_csrf.py.
"""
import pytest
from database import db
from models import Product, ProductComment, ProductReaction


def _login(client, login_fixture, u):
    assert login_fixture(u['username'], u['password']).status_code == 302


# ═══════════════════════════════════════════════════════════════
# GET /api/products/<id>/comments
# ═══════════════════════════════════════════════════════════════
def test_get_comments_empty(client, make_active_store, make_product):
    s = make_active_store()
    p = make_product(s['id'])
    r = client.get(f'/api/products/{p["id"]}/comments')
    assert r.status_code == 200
    assert r.get_json()['comments'] == []


def test_get_comments_returns_existing(
    client, app, make_user, make_active_store, make_product
):
    from models import User
    s = make_active_store()
    p = make_product(s['id'])
    u = make_user(username='commenter1')
    with app.app_context():
        c = ProductComment(product_id=p['id'], user_id=u['id'], text='hello world')
        db.session.add(c)
        db.session.commit()

    r = client.get(f'/api/products/{p["id"]}/comments')
    assert r.status_code == 200
    data = r.get_json()
    assert len(data['comments']) == 1
    assert data['comments'][0]['text'] == 'hello world'
    assert data['comments'][0]['username'] == 'commenter1'


def test_get_comments_404_for_missing_product(client):
    r = client.get('/api/products/999999/comments')
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# POST /api/products/<id>/comments
# ═══════════════════════════════════════════════════════════════
def test_add_comment_requires_auth(client, make_active_store, make_product):
    s = make_active_store()
    p = make_product(s['id'])
    r = client.post(f'/api/products/{p["id"]}/comments', json={'text': 'anon'})
    assert r.status_code == 401


def test_add_comment_success(
    client, app, make_user, make_active_store, make_product, login
):
    u = make_user(username='adder1')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'])

    r = client.post(f'/api/products/{p["id"]}/comments', json={'text': 'my comment'})
    assert r.status_code == 201
    data = r.get_json()
    assert data['comment']['text'] == 'my comment'
    with app.app_context():
        assert ProductComment.query.filter_by(product_id=p['id']).count() == 1


def test_add_comment_rejects_empty(
    client, make_user, make_active_store, make_product, login
):
    u = make_user(username='adder2')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'])
    r = client.post(f'/api/products/{p["id"]}/comments', json={'text': '   '})
    assert r.status_code == 400


def test_add_comment_404_for_missing_product(client, make_user, login):
    u = make_user(username='adder3')
    _login(client, login, u)
    r = client.post('/api/products/999999/comments', json={'text': 'x'})
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# PUT /api/comments/<id>
# ═══════════════════════════════════════════════════════════════
def test_edit_comment_owner(
    client, app, make_user, make_active_store, make_product, login
):
    u = make_user(username='editor1')
    s = make_active_store()
    p = make_product(s['id'])
    with app.app_context():
        c = ProductComment(product_id=p['id'], user_id=u['id'], text='original')
        db.session.add(c)
        db.session.commit()
        cid = c.id

    _login(client, login, u)
    r = client.put(f'/api/comments/{cid}', json={'text': 'edited'})
    assert r.status_code == 200
    with app.app_context():
        c = db.session.get(ProductComment, cid)
        assert c.text == 'edited'


def test_edit_comment_rejects_other_user(
    client, app, make_user, make_active_store, make_product, login
):
    author = make_user(username='author_e')
    other = make_user(username='other_e')
    s = make_active_store()
    p = make_product(s['id'])
    with app.app_context():
        c = ProductComment(product_id=p['id'], user_id=author['id'], text='x')
        db.session.add(c)
        db.session.commit()
        cid = c.id

    _login(client, login, other)
    r = client.put(f'/api/comments/{cid}', json={'text': 'hacked'})
    assert r.status_code == 403
    with app.app_context():
        c = db.session.get(ProductComment, cid)
        assert c.text == 'x'


def test_edit_comment_rejects_empty(
    client, app, make_user, make_active_store, make_product, login
):
    u = make_user(username='editor2')
    s = make_active_store()
    p = make_product(s['id'])
    with app.app_context():
        c = ProductComment(product_id=p['id'], user_id=u['id'], text='original')
        db.session.add(c)
        db.session.commit()
        cid = c.id

    _login(client, login, u)
    r = client.put(f'/api/comments/{cid}', json={'text': ''})
    assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# DELETE /api/comments/<id>
# ═══════════════════════════════════════════════════════════════
def test_delete_comment_owner(
    client, app, make_user, make_active_store, make_product, login
):
    u = make_user(username='del_owner')
    s = make_active_store()
    p = make_product(s['id'])
    with app.app_context():
        c = ProductComment(product_id=p['id'], user_id=u['id'], text='to delete')
        db.session.add(c)
        db.session.commit()
        cid = c.id

    _login(client, login, u)
    r = client.delete(f'/api/comments/{cid}')
    assert r.status_code == 200
    with app.app_context():
        assert db.session.get(ProductComment, cid) is None


def test_delete_comment_rejects_other_user(
    client, app, make_user, make_active_store, make_product, login
):
    author = make_user(username='author_d')
    other = make_user(username='other_d')
    s = make_active_store()
    p = make_product(s['id'])
    with app.app_context():
        c = ProductComment(product_id=p['id'], user_id=author['id'], text='x')
        db.session.add(c)
        db.session.commit()
        cid = c.id

    _login(client, login, other)
    r = client.delete(f'/api/comments/{cid}')
    assert r.status_code == 403
    with app.app_context():
        assert db.session.get(ProductComment, cid) is not None


# ═══════════════════════════════════════════════════════════════
# POST /api/products/<id>/reaction
# ═══════════════════════════════════════════════════════════════
def test_react_requires_auth(client, make_active_store, make_product):
    s = make_active_store()
    p = make_product(s['id'])
    r = client.post(f'/api/products/{p["id"]}/reaction', json={'reaction_type': 'like'})
    assert r.status_code == 401


def test_react_invalid_type(
    client, make_user, make_active_store, make_product, login
):
    u = make_user(username='react_inv')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'])
    r = client.post(f'/api/products/{p["id"]}/reaction', json={'reaction_type': 'bogus'})
    assert r.status_code == 400


def test_react_add(
    client, app, make_user, make_active_store, make_product, login
):
    u = make_user(username='react_add')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'])
    r = client.post(f'/api/products/{p["id"]}/reaction', json={'reaction_type': 'like'})
    assert r.status_code == 201
    with app.app_context():
        assert ProductReaction.query.filter_by(product_id=p['id'], user_id=u['id']).count() == 1


def test_react_toggle_same_removes(
    client, app, make_user, make_active_store, make_product, login
):
    u = make_user(username='react_tog')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'])
    client.post(f'/api/products/{p["id"]}/reaction', json={'reaction_type': 'like'})
    r = client.post(f'/api/products/{p["id"]}/reaction', json={'reaction_type': 'like'})
    assert r.status_code == 200
    assert 'إزالة' in r.get_json()['message']
    with app.app_context():
        assert ProductReaction.query.filter_by(product_id=p['id'], user_id=u['id']).count() == 0


def test_react_change_type(
    client, app, make_user, make_active_store, make_product, login
):
    u = make_user(username='react_chg')
    _login(client, login, u)
    s = make_active_store()
    p = make_product(s['id'])
    client.post(f'/api/products/{p["id"]}/reaction', json={'reaction_type': 'like'})
    r = client.post(f'/api/products/{p["id"]}/reaction', json={'reaction_type': 'love'})
    assert r.status_code == 200
    with app.app_context():
        react = ProductReaction.query.filter_by(product_id=p['id'], user_id=u['id']).first()
        assert react.reaction_type == 'love'
