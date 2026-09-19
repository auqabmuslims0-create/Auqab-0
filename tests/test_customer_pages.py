"""
اختبارات الصفحات العامة للزبون (market, stores, offers, services, account).

التركيز على:
- الصفحات العامة تعمل للزوار
- المنتجات من متاجر معطّلة لا تُعرض
- فلاتر البحث والترتيب
- AJAX fragments
- عزل المفضلة والتقييمات (لكل مستخدم)
"""
import pytest
from datetime import timedelta
from database import db
from models import User, Store, Product, Favorite, Review, Subscription
from shared.time_utils import current_time


def _login(client, login_fixture, u):
    assert login_fixture(u['username'], u['password']).status_code == 302


def _make_store_with_sub(app, owner_id, status='active', has_delivery=False, name=None):
    """متجر مع اشتراك paid ساري (لكي يجتاز is_store_active)."""
    s = Store(
        owner_id=owner_id,
        name=name or 'CustStore',
        subscription_status=status,
        has_delivery=has_delivery,
        latitude=33.5, longitude=36.3,
    )
    db.session.add(s)
    db.session.flush()
    if status == 'active':
        sub = Subscription(
            user_id=owner_id, store_id=s.id,
            start_date=current_time(),
            end_date=current_time() + timedelta(days=30),
            amount=500.0, status='paid', duration_days=30,
        )
        db.session.add(sub)
        db.session.flush()
        s.subscription_expiry = sub.end_date
    db.session.commit()
    return s.id


# ═══════════════════════════════════════════════════════════════
# /market
# ═══════════════════════════════════════════════════════════════
def test_market_accessible_to_anonymous(client):
    r = client.get('/market')
    assert r.status_code == 200


def test_market_excludes_inactive_store_products(client, app, make_user, make_product):
    owner = make_user(username='cp_own1', role='owner')
    sid_active = _make_store_with_sub(app, owner['id'], status='active', name='ActiveS')
    sid_susp = _make_store_with_sub(app, owner['id'], status='suspended', name='SuspS')
    make_product(sid_active, name='VisibleProd')
    make_product(sid_susp, name='HiddenProd')

    r = client.get('/market')
    assert r.status_code == 200
    body = r.data.decode('utf-8')
    assert 'VisibleProd' in body
    assert 'HiddenProd' not in body


def test_market_filter_by_category(client, app, make_user, make_product):
    from models import Category
    owner = make_user(username='cp_own2', role='owner')
    sid = _make_store_with_sub(app, owner['id'])
    with app.app_context():
        cat = Category(name='TestCat', store_id=sid)
        db.session.add(cat)
        db.session.commit()
        cat_id = cat.id
    make_product(sid, name='CatFilterProd')

    r = client.get(f'/market?category_id={cat_id}')
    assert r.status_code == 200


def test_market_filter_by_price_range(client, app, make_user, make_product):
    owner = make_user(username='cp_own3', role='owner')
    sid = _make_store_with_sub(app, owner['id'])
    make_product(sid, name='CheapProd', price=50)
    make_product(sid, name='ExpensiveProd', price=5000)

    r = client.get('/market?min_price=100&max_price=2000')
    assert r.status_code == 200
    body = r.data.decode('utf-8')
    assert 'CheapProd' not in body
    assert 'ExpensiveProd' not in body


def test_market_search_by_name(client, app, make_user, make_product):
    owner = make_user(username='cp_own4', role='owner')
    sid = _make_store_with_sub(app, owner['id'])
    make_product(sid, name='UniqueNameXYZ')
    make_product(sid, name='OtherProduct')

    r = client.get('/market?q=UniqueNameXYZ')
    assert r.status_code == 200
    body = r.data.decode('utf-8')
    assert 'UniqueNameXYZ' in body
    assert 'OtherProduct' not in body


def test_market_invalid_sort_falls_back(client):
    r = client.get('/market?sort=bogus_sort')
    assert r.status_code == 200


def test_market_ajax_returns_json(client):
    r = client.get('/market?format=json')
    assert r.status_code == 200
    data = r.get_json()
    assert 'html' in data
    assert 'has_next' in data
    assert 'total' in data


def test_market_ajax_via_xhr_header(client):
    r = client.get('/market', headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 200
    data = r.get_json()
    assert 'html' in data


# ═══════════════════════════════════════════════════════════════
# /search_suggestions
# ═══════════════════════════════════════════════════════════════
def test_search_suggestions_empty_for_short_query(client):
    r = client.get('/search_suggestions?q=a')
    assert r.status_code == 200
    data = r.get_json()
    assert data['stores'] == []
    assert data['products'] == []


def test_search_suggestions_finds_products(client, app, make_user, make_product):
    owner = make_user(username='cp_own5', role='owner')
    sid = _make_store_with_sub(app, owner['id'])
    make_product(sid, name='QueryableItem')

    r = client.get('/search_suggestions?q=Queryable')
    assert r.status_code == 200
    data = r.get_json()
    names = [p['name'] for p in data['products']]
    assert 'QueryableItem' in names


def test_search_suggestions_excludes_inactive_stores(client, app, make_user, make_product):
    owner = make_user(username='cp_own6', role='owner')
    sid = _make_store_with_sub(app, owner['id'], status='suspended')
    make_product(sid, name='HiddenSuggest')

    r = client.get('/search_suggestions?q=HiddenSuggest')
    data = r.get_json()
    names = [p['name'] for p in data['products']]
    assert 'HiddenSuggest' not in names


# ═══════════════════════════════════════════════════════════════
# /api/active-shoppers
# ═══════════════════════════════════════════════════════════════
def test_active_shoppers_endpoint(client):
    r = client.get('/api/active-shoppers')
    assert r.status_code == 200
    data = r.get_json()
    assert 'active_shoppers_count' in data
    assert isinstance(data['active_shoppers_count'], int)


# ═══════════════════════════════════════════════════════════════
# / (home) — redirect by role
# ═══════════════════════════════════════════════════════════════
def test_home_redirects_anonymous_to_login(client):
    r = client.get('/')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_home_redirects_customer_to_market(client, make_user, login):
    u = make_user(username='cp_home_c', role='customer')
    _login(client, login, u)
    r = client.get('/')
    assert r.status_code == 302
    assert '/market' in r.headers['Location']


def test_home_redirects_owner_to_stores(client, make_user, login):
    u = make_user(username='cp_home_o', role='owner')
    _login(client, login, u)
    r = client.get('/')
    assert r.status_code == 302
    assert 'my_stores' in r.headers['Location'] or '/store' in r.headers['Location']


def test_home_redirects_admin_to_dashboard(client, make_user, login):
    u = make_user(username='cp_home_a', role='admin')
    _login(client, login, u)
    r = client.get('/')
    assert r.status_code == 302
    assert '/admin' in r.headers['Location']


# ═══════════════════════════════════════════════════════════════
# /stores
# ═══════════════════════════════════════════════════════════════
def test_stores_page_anonymous(client):
    r = client.get('/stores')
    assert r.status_code == 200


def test_stores_page_lists_active_only(client, app, make_user):
    owner = make_user(username='cp_own7', role='owner')
    _make_store_with_sub(app, owner['id'], status='active', name='VisibleStoreX')
    _make_store_with_sub(app, owner['id'], status='suspended', name='HiddenStoreX')

    r = client.get('/stores')
    body = r.data.decode('utf-8')
    assert 'VisibleStoreX' in body
    assert 'HiddenStoreX' not in body


def test_stores_page_ajax(client):
    r = client.get('/stores?format=json')
    assert r.status_code == 200
    data = r.get_json()
    assert 'html' in data


def test_stores_filter_open(client, app, make_user):
    owner = make_user(username='cp_own8', role='owner')
    _make_store_with_sub(app, owner['id'], status='active', name='MaybeOpen')
    r = client.get('/stores?status=open')
    assert r.status_code == 200


def test_stores_filter_closed(client, app, make_user):
    owner = make_user(username='cp_own9', role='owner')
    _make_store_with_sub(app, owner['id'], status='active', name='MaybeClosed')
    r = client.get('/stores?status=closed')
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════
# /store/<id>/public
# ═══════════════════════════════════════════════════════════════
def test_store_public_anonymous(client, app, make_user):
    owner = make_user(username='cp_own10', role='owner')
    sid = _make_store_with_sub(app, owner['id'])
    r = client.get(f'/store/{sid}/public')
    assert r.status_code == 200


def test_store_public_404_for_suspended(client, app, make_user):
    owner = make_user(username='cp_own11', role='owner')
    sid = _make_store_with_sub(app, owner['id'], status='suspended')
    r = client.get(f'/store/{sid}/public')
    assert r.status_code == 404


def test_store_public_404_for_missing(client):
    r = client.get('/store/999999/public')
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════
# /product/<id>
# ═══════════════════════════════════════════════════════════════
def test_product_public_anonymous(client, app, make_user, make_product):
    owner = make_user(username='cp_own12', role='owner')
    sid = _make_store_with_sub(app, owner['id'])
    p = make_product(sid, name='PublicProductY')
    r = client.get(f'/product/{p["id"]}')
    assert r.status_code == 200
    assert b'PublicProductY' in r.data


def test_product_public_404_for_inactive_store(client, app, make_user, make_product):
    owner = make_user(username='cp_own13', role='owner')
    sid = _make_store_with_sub(app, owner['id'], status='suspended')
    p = make_product(sid)
    r = client.get(f'/product/{p["id"]}')
    assert r.status_code == 404


def test_product_public_404_for_missing(client):
    r = client.get('/product/999999')
    assert r.status_code == 404


def test_product_view_increments_counter(client, app, make_user, make_product):
    owner = make_user(username='cp_own14', role='owner')
    sid = _make_store_with_sub(app, owner['id'])
    p = make_product(sid)

    with app.app_context():
        initial = db.session.get(Product, p['id']).views or 0

    client.get(f'/product/{p["id"]}')

    with app.app_context():
        after = db.session.get(Product, p['id']).views or 0
        assert after == initial + 1


# ═══════════════════════════════════════════════════════════════
# /offers
# ═══════════════════════════════════════════════════════════════
def test_offers_page_anonymous(client):
    r = client.get('/offers')
    assert r.status_code == 200


def test_offers_only_active_store_offers(client, app, make_user, make_product):
    owner = make_user(username='cp_own15', role='owner')
    sid_active = _make_store_with_sub(app, owner['id'], status='active', name='ActOff')
    sid_susp = _make_store_with_sub(app, owner['id'], status='suspended', name='SusOff')
    make_product(sid_active, name='VisibleOffer', is_offer=True)
    make_product(sid_susp, name='HiddenOffer', is_offer=True)

    r = client.get('/offers')
    body = r.data.decode('utf-8')
    assert 'VisibleOffer' in body
    assert 'HiddenOffer' not in body


def test_offers_excludes_non_offers(client, app, make_user, make_product):
    owner = make_user(username='cp_own16', role='owner')
    sid = _make_store_with_sub(app, owner['id'])
    make_product(sid, name='RegularProd', is_offer=False)

    r = client.get('/offers')
    assert b'RegularProd' not in r.data


def test_offers_ajax(client):
    r = client.get('/offers?format=json')
    assert r.status_code == 200
    assert 'html' in r.get_json()


# ═══════════════════════════════════════════════════════════════
# /services
# ═══════════════════════════════════════════════════════════════
def test_services_page_anonymous(client):
    r = client.get('/services')
    assert r.status_code == 200


def test_support_requires_login(client):
    r = client.get('/support')
    assert r.status_code == 302


def test_contact_redirects_to_support(client, make_user, login):
    u = make_user(username='cp_c_sup')
    _login(client, login, u)
    r = client.get('/contact')
    assert r.status_code == 302
    assert 'support' in r.headers['Location']


def test_contact_send_requires_login(client):
    r = client.post('/contact/send', data={'message': 'hello'})
    assert r.status_code == 302


def test_contact_send_no_admin(client, app, make_user, login):
    """لا يوجد admin نشط → 404 على AJAX."""
    u = make_user(username='cp_c_1')
    _login(client, login, u)
    r = client.post('/contact/send',
                    data={'message': 'hi'},
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 404


def test_contact_send_success(client, app, make_user, login):
    admin = make_user(username='cp_admin_1', role='admin')
    u = make_user(username='cp_c_2')
    _login(client, login, u)
    r = client.post('/contact/send',
                    data={'message': 'مرحباً بك'},
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 200
    assert r.get_json()['status'] == 'success'

    from models import ChatMessage
    with app.app_context():
        msgs = ChatMessage.query.filter_by(sender_id=u['id']).all()
        assert len(msgs) == 1
        assert msgs[0].message == 'مرحباً بك'


def test_contact_send_empty_message_rejected(client, app, make_user, login):
    make_user(username='cp_admin_2', role='admin')
    u = make_user(username='cp_c_3')
    _login(client, login, u)
    r = client.post('/contact/send',
                    data={'message': '   '},
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# /favorites
# ═══════════════════════════════════════════════════════════════
def test_favorites_page_requires_login(client):
    r = client.get('/favorites')
    assert r.status_code == 302


def test_favorites_page_lists_user_favorites(client, app, make_user, login, make_product):
    owner = make_user(username='cp_own17', role='owner')
    sid = _make_store_with_sub(app, owner['id'])
    p = make_product(sid, name='FavProductZ')

    u = make_user(username='cp_fav_u')
    with app.app_context():
        db.session.add(Favorite(user_id=u['id'], product_id=p['id']))
        db.session.commit()

    _login(client, login, u)
    r = client.get('/favorites')
    assert r.status_code == 200
    assert b'FavProductZ' in r.data


def test_favorite_toggle_product_add_remove(client, app, make_user, login, make_product):
    owner = make_user(username='cp_own18', role='owner')
    sid = _make_store_with_sub(app, owner['id'])
    p = make_product(sid)
    u = make_user(username='cp_fav_t')
    _login(client, login, u)

    # Add
    r = client.post('/favorite/toggle/product/' + str(p['id']))
    assert r.status_code == 302
    with app.app_context():
        assert Favorite.query.filter_by(user_id=u['id'], product_id=p['id']).count() == 1

    # Remove
    r = client.post('/favorite/toggle/product/' + str(p['id']))
    assert r.status_code == 302
    with app.app_context():
        assert Favorite.query.filter_by(user_id=u['id'], product_id=p['id']).count() == 0


def test_favorite_toggle_store(client, app, make_user, login):
    owner = make_user(username='cp_own19', role='owner')
    sid = _make_store_with_sub(app, owner['id'])
    u = make_user(username='cp_fav_s')
    _login(client, login, u)

    r = client.post(f'/favorite/toggle/store/{sid}')
    assert r.status_code == 302
    with app.app_context():
        assert Favorite.query.filter_by(user_id=u['id'], store_id=sid).count() == 1


def test_favorite_toggle_rejects_bad_type(client, make_user, login):
    u = make_user(username='cp_fav_b')
    _login(client, login, u)
    r = client.post('/favorite/toggle',
                    json={'type': 'bogus', 'id': 1})
    assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# /product/<id>/review
# ═══════════════════════════════════════════════════════════════
def test_add_review_requires_login(client, app, make_user, make_product):
    owner = make_user(username='cp_own20', role='owner')
    sid = _make_store_with_sub(app, owner['id'])
    p = make_product(sid)
    r = client.post(f'/product/{p["id"]}/review',
                    data={'rating': '5', 'comment': 'great'})
    assert r.status_code == 302


def test_add_review_success(client, app, make_user, login, make_product):
    owner = make_user(username='cp_own21', role='owner')
    sid = _make_store_with_sub(app, owner['id'])
    p = make_product(sid)
    u = make_user(username='cp_rev_1')
    _login(client, login, u)

    r = client.post(f'/product/{p["id"]}/review',
                    data={'rating': '5', 'comment': 'ممتاز'},
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 200
    with app.app_context():
        assert Review.query.filter_by(user_id=u['id'], product_id=p['id']).count() == 1


def test_add_review_updates_existing(client, app, make_user, login, make_product):
    owner = make_user(username='cp_own22', role='owner')
    sid = _make_store_with_sub(app, owner['id'])
    p = make_product(sid)
    u = make_user(username='cp_rev_2')

    with app.app_context():
        db.session.add(Review(user_id=u['id'], product_id=p['id'], rating=3, comment='ok'))
        db.session.commit()

    _login(client, login, u)
    r = client.post(f'/product/{p["id"]}/review',
                    data={'rating': '5', 'comment': 'محدث'},
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 200
    with app.app_context():
        revs = Review.query.filter_by(user_id=u['id'], product_id=p['id']).all()
        assert len(revs) == 1
        assert revs[0].rating == 5
        assert revs[0].comment == 'محدث'


def test_add_review_rejects_invalid_rating(client, app, make_user, login, make_product):
    owner = make_user(username='cp_own23', role='owner')
    sid = _make_store_with_sub(app, owner['id'])
    p = make_product(sid)
    u = make_user(username='cp_rev_3')
    _login(client, login, u)

    r = client.post(f'/product/{p["id"]}/review',
                    data={'rating': '10', 'comment': 'x'},
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 400


def test_add_review_rejects_empty_comment(client, app, make_user, login, make_product):
    owner = make_user(username='cp_own24', role='owner')
    sid = _make_store_with_sub(app, owner['id'])
    p = make_product(sid)
    u = make_user(username='cp_rev_4')
    _login(client, login, u)

    r = client.post(f'/product/{p["id"]}/review',
                    data={'rating': '5', 'comment': ''},
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 400
