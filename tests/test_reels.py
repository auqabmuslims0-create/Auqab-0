"""
اختبارات reels_bp — العرض، المشاهدات، والتفاعلات.

ملاحظة: get_feed_query يفلتر بـ Reel.is_active == True + Store active.
"""
import pytest
from database import db
from models import Reel, ReelReaction, Store, User


def _login(client, login_fixture, u):
    assert login_fixture(u['username'], u['password']).status_code == 302


def _make_reel(app, store_id, caption='Test Reel', is_active=True, views=0, video_url='x.mp4'):
    """إنشاء Reel مباشرة في DB. يعيد reel_id."""
    with app.app_context():
        reel = Reel(
            store_id=store_id,
            video_url=video_url,
            caption=caption,
            is_active=is_active,
            views=views,
        )
        db.session.add(reel)
        db.session.commit()
        return reel.id


# ═══════════════════════════════════════════════════════════════
# GET /reels (HTML)
# ═══════════════════════════════════════════════════════════════
def test_reels_page_anonymous(client):
    r = client.get('/reels')
    assert r.status_code == 200


def test_reels_page_authenticated(client, make_user, login):
    u = make_user(username='reels_u1')
    _login(client, login, u)
    r = client.get('/reels')
    assert r.status_code == 200


def test_reels_page_json_fragment(client, app, make_active_store):
    s = make_active_store()
    _make_reel(app, s['id'])
    r = client.get('/reels?format=json')
    assert r.status_code == 200
    data = r.get_json()
    assert 'html' in data
    assert 'has_next' in data


def test_reels_page_ajax_header(client, app, make_active_store):
    s = make_active_store()
    _make_reel(app, s['id'])
    r = client.get('/reels', headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 200
    data = r.get_json()
    assert 'html' in data


# ═══════════════════════════════════════════════════════════════
# GET /api/reels
# ═══════════════════════════════════════════════════════════════
def test_api_reels_empty(client):
    r = client.get('/api/reels')
    assert r.status_code == 200
    data = r.get_json()
    assert data['reels'] == []
    assert data['has_next'] is False


def test_api_reels_returns_active_only(client, app, make_active_store):
    s = make_active_store()
    _make_reel(app, s['id'], caption='active')
    _make_reel(app, s['id'], caption='hidden', is_active=False)
    r = client.get('/api/reels')
    assert r.status_code == 200
    data = r.get_json()
    captions = [r['caption'] for r in data['reels']]
    assert 'active' in captions
    assert 'hidden' not in captions


def test_api_reels_inactive_store_excluded(client, app, make_user, make_store):
    owner = make_user(username='reels_own1', role='owner')
    inactive = make_store(owner_id=owner['id'], subscription_status='suspended')
    _make_reel(app, inactive['id'])
    r = client.get('/api/reels')
    assert r.status_code == 200
    assert r.get_json()['reels'] == []


def test_api_reels_sort_invalid_falls_back(client, app, make_active_store):
    s = make_active_store()
    _make_reel(app, s['id'])
    r = client.get('/api/reels?sort=bogus')
    assert r.status_code == 200
    assert r.get_json()['sort'] == 'views'


def test_api_reels_sort_views(client, app, make_active_store):
    s = make_active_store()
    _make_reel(app, s['id'], caption='low', views=1)
    _make_reel(app, s['id'], caption='high', views=100)
    r = client.get('/api/reels?sort=views')
    assert r.status_code == 200
    reels = r.get_json()['reels']
    assert reels[0]['caption'] == 'high'


def test_api_reels_sort_newest(client, app, make_active_store):
    s = make_active_store()
    _make_reel(app, s['id'], caption='first')
    _make_reel(app, s['id'], caption='second')
    r = client.get('/api/reels?sort=newest')
    assert r.status_code == 200
    reels = r.get_json()['reels']
    assert reels[0]['caption'] == 'second'


def test_api_reels_per_page(client, app, make_active_store):
    s = make_active_store()
    for i in range(5):
        _make_reel(app, s['id'], caption=f'r{i}')
    r = client.get('/api/reels?per_page=2')
    assert r.status_code == 200
    assert len(r.get_json()['reels']) == 2
    assert r.get_json()['has_next'] is True


# ═══════════════════════════════════════════════════════════════
# POST /api/reels/<id>/view
# ═══════════════════════════════════════════════════════════════
def test_record_view_increments(client, app, make_active_store):
    s = make_active_store()
    rid = _make_reel(app, s['id'], views=5)
    r = client.post(f'/api/reels/{rid}/view')
    assert r.status_code == 200
    with app.app_context():
        reel = db.session.get(Reel, rid)
        assert reel.views == 6


def test_record_view_missing_reel(client):
    """لا يستخدم get_or_404 — view يبتلع الأخطاء بصمت."""
    r = client.post('/api/reels/999999/view')
    # service يعيد None بصمت لعدم وجود الريل؛ 200 مقبول
    assert r.status_code in (200, 404)


# ═══════════════════════════════════════════════════════════════
# POST /api/reels/<id>/reaction
# ═══════════════════════════════════════════════════════════════
def test_reel_reaction_requires_auth(client, app, make_active_store):
    s = make_active_store()
    rid = _make_reel(app, s['id'])
    r = client.post(f'/api/reels/{rid}/reaction', json={'reaction_type': 'like'})
    assert r.status_code == 401


def test_reel_reaction_invalid_type(client, app, make_user, make_active_store, login):
    u = make_user(username='rr_inv')
    s = make_active_store()
    rid = _make_reel(app, s['id'])
    _login(client, login, u)
    r = client.post(f'/api/reels/{rid}/reaction', json={'reaction_type': 'bogus'})
    assert r.status_code == 400


def test_reel_reaction_add(
    client, app, make_user, make_active_store, login
):
    u = make_user(username='rr_add')
    s = make_active_store()
    rid = _make_reel(app, s['id'])
    _login(client, login, u)
    r = client.post(f'/api/reels/{rid}/reaction', json={'reaction_type': 'like'})
    assert r.status_code == 200
    with app.app_context():
        assert ReelReaction.query.filter_by(reel_id=rid, user_id=u['id']).count() == 1


def test_reel_reaction_toggle_removes(
    client, app, make_user, make_active_store, login
):
    u = make_user(username='rr_tog')
    s = make_active_store()
    rid = _make_reel(app, s['id'])
    _login(client, login, u)
    client.post(f'/api/reels/{rid}/reaction', json={'reaction_type': 'like'})
    r = client.post(f'/api/reels/{rid}/reaction', json={'reaction_type': 'like'})
    assert r.status_code == 200
    assert r.get_json()['result'].get('removed') is True
    with app.app_context():
        assert ReelReaction.query.filter_by(reel_id=rid, user_id=u['id']).count() == 0


def test_reel_reaction_change_type(
    client, app, make_user, make_active_store, login
):
    u = make_user(username='rr_chg')
    s = make_active_store()
    rid = _make_reel(app, s['id'])
    _login(client, login, u)
    client.post(f'/api/reels/{rid}/reaction', json={'reaction_type': 'like'})
    r = client.post(f'/api/reels/{rid}/reaction', json={'reaction_type': 'love'})
    assert r.status_code == 200
    assert r.get_json()['result'].get('updated') is True
    with app.app_context():
        react = ReelReaction.query.filter_by(reel_id=rid, user_id=u['id']).first()
        assert react.reaction_type == 'love'


def test_reel_reaction_missing_reel(client, app, make_user, login):
    u = make_user(username='rr_missing')
    _login(client, login, u)
    r = client.post('/api/reels/999999/reaction', json={'reaction_type': 'like'})
    assert r.status_code == 404
