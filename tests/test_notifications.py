"""
اختبارات notifications_bp — إشعارات المستخدم + Push subscription.

ملاحظة: كل مسارات /api/notifications/* تستخدم @login_required (session)،
لا JWT. الزوار يُحوَّلون إلى /login (302) وليس 401.
"""
import pytest
from database import db
from models import Notification, PushSubscription


def _login(client, login_fixture, u):
    assert login_fixture(u['username'], u['password']).status_code == 302


def _make_notif(app, user_id, title='T', message='msg',
                type_='info', is_read=False, priority='normal', link=None):
    with app.app_context():
        n = Notification(
            user_id=user_id, title=title, message=message,
            type=type_, is_read=is_read, priority=priority, link=link,
        )
        db.session.add(n)
        db.session.commit()
        return n.id


# ═══════════════════════════════════════════════════════════════
# صفحة HTML
# ═══════════════════════════════════════════════════════════════
def test_notifications_page_anonymous_redirects(client):
    r = client.get('/notifications')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_notifications_page_authenticated(client, make_user, login):
    u = make_user(username='np_ok')
    _login(client, login, u)
    r = client.get('/notifications')
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════
# unread-count + counts
# ═══════════════════════════════════════════════════════════════
def test_unread_count_zero(client, make_user, login):
    u = make_user(username='uc_zero')
    _login(client, login, u)
    r = client.get('/api/notifications/unread-count')
    assert r.status_code == 200
    assert r.get_json()['unread_count'] == 0


def test_unread_count_accurate(client, app, make_user, login):
    u = make_user(username='uc_ok')
    _make_notif(app, u['id'], is_read=False)
    _make_notif(app, u['id'], is_read=False)
    _make_notif(app, u['id'], is_read=True)
    _login(client, login, u)
    r = client.get('/api/notifications/unread-count')
    assert r.get_json()['unread_count'] == 2


def test_counts_breakdown(client, app, make_user, login):
    u = make_user(username='cnt_ok')
    _make_notif(app, u['id'], type_='order')
    _make_notif(app, u['id'], type_='order')
    _make_notif(app, u['id'], type_='alert', is_read=True)
    _login(client, login, u)
    r = client.get('/api/notifications/counts')
    assert r.status_code == 200
    data = r.get_json()
    assert data['total'] == 3
    assert data['unread'] == 2
    assert data['by_type']['order'] == 2
    assert data['by_type']['alert'] == 1


# ═══════════════════════════════════════════════════════════════
# GET /api/notifications
# ═══════════════════════════════════════════════════════════════
def test_get_notifications_empty(client, make_user, login):
    u = make_user(username='gn_empty')
    _login(client, login, u)
    r = client.get('/api/notifications')
    assert r.status_code == 200
    data = r.get_json()
    assert data['notifications'] == []
    assert data['pagination']['total'] == 0


def test_get_notifications_only_own(client, app, make_user, login):
    u1 = make_user(username='gn_u1')
    u2 = make_user(username='gn_u2')
    _make_notif(app, u1['id'], title='Mine')
    _make_notif(app, u2['id'], title='Theirs')
    _login(client, login, u1)
    r = client.get('/api/notifications')
    titles = [n['title'] for n in r.get_json()['notifications']]
    assert 'Mine' in titles
    assert 'Theirs' not in titles


def test_get_notifications_pagination(client, app, make_user, login):
    u = make_user(username='gn_pg')
    for i in range(5):
        _make_notif(app, u['id'], title=f'n{i}')
    _login(client, login, u)
    r = client.get('/api/notifications?per_page=2&page=1')
    data = r.get_json()
    assert len(data['notifications']) == 2
    assert data['pagination']['total'] == 5
    assert data['pagination']['total_pages'] == 3
    assert data['pagination']['has_next'] is True
    assert data['pagination']['has_prev'] is False


def test_get_notifications_filter_unread(client, app, make_user, login):
    u = make_user(username='gn_ur')
    _make_notif(app, u['id'], title='u1', is_read=False)
    _make_notif(app, u['id'], title='r1', is_read=True)
    _login(client, login, u)
    r = client.get('/api/notifications?read=false')
    titles = [n['title'] for n in r.get_json()['notifications']]
    assert titles == ['u1']


def test_get_notifications_filter_by_type(client, app, make_user, login):
    u = make_user(username='gn_ty')
    _make_notif(app, u['id'], title='o', type_='order')
    _make_notif(app, u['id'], title='s', type_='subscription')
    _login(client, login, u)
    r = client.get('/api/notifications?type=order')
    titles = [n['title'] for n in r.get_json()['notifications']]
    assert titles == ['o']


def test_get_notifications_anonymous_redirects(client):
    r = client.get('/api/notifications')
    assert r.status_code == 302


# ═══════════════════════════════════════════════════════════════
# mark_read / read-all
# ═══════════════════════════════════════════════════════════════
def test_mark_read_success(client, app, make_user, login):
    u = make_user(username='mr_ok')
    nid = _make_notif(app, u['id'])
    _login(client, login, u)
    r = client.post(f'/api/notifications/{nid}/read')
    assert r.status_code == 200
    with app.app_context():
        n = db.session.get(Notification, nid)
        assert n.is_read is True
        assert n.read_at is not None


def test_mark_read_rejects_other_user(client, app, make_user, login):
    u1 = make_user(username='mr_u1')
    u2 = make_user(username='mr_u2')
    nid = _make_notif(app, u1['id'])
    _login(client, login, u2)
    r = client.post(f'/api/notifications/{nid}/read')
    assert r.status_code == 400
    with app.app_context():
        assert db.session.get(Notification, nid).is_read is False


def test_mark_read_not_found(client, make_user, login):
    u = make_user(username='mr_nf')
    _login(client, login, u)
    r = client.post('/api/notifications/999999/read')
    assert r.status_code == 400


def test_mark_all_read(client, app, make_user, login):
    u = make_user(username='mar_ok')
    _make_notif(app, u['id'], is_read=False)
    _make_notif(app, u['id'], is_read=False)
    _login(client, login, u)
    r = client.post('/api/notifications/read-all')
    assert r.status_code == 200
    assert r.get_json()['unread_count'] == 0
    with app.app_context():
        assert Notification.query.filter_by(user_id=u['id'], is_read=False).count() == 0


# ═══════════════════════════════════════════════════════════════
# delete single / delete read / delete selected
# ═══════════════════════════════════════════════════════════════
def test_delete_notification(client, app, make_user, login):
    u = make_user(username='dn_ok')
    nid = _make_notif(app, u['id'])
    _login(client, login, u)
    r = client.delete(f'/api/notifications/{nid}')
    assert r.status_code == 200
    with app.app_context():
        assert db.session.get(Notification, nid) is None


def test_delete_notification_rejects_other_user(client, app, make_user, login):
    u1 = make_user(username='dn_u1')
    u2 = make_user(username='dn_u2')
    nid = _make_notif(app, u1['id'])
    _login(client, login, u2)
    r = client.delete(f'/api/notifications/{nid}')
    assert r.status_code == 400
    with app.app_context():
        assert db.session.get(Notification, nid) is not None


def test_delete_all_read(client, app, make_user, login):
    u = make_user(username='dar_ok')
    _make_notif(app, u['id'], is_read=True)
    _make_notif(app, u['id'], is_read=True)
    _make_notif(app, u['id'], is_read=False)
    _login(client, login, u)
    r = client.delete('/api/notifications/read')
    assert r.status_code == 200
    with app.app_context():
        assert Notification.query.filter_by(user_id=u['id']).count() == 1


def test_delete_selected(client, app, make_user, login):
    u = make_user(username='dsel_ok')
    a = _make_notif(app, u['id'])
    b = _make_notif(app, u['id'])
    _make_notif(app, u['id'])
    _login(client, login, u)
    r = client.post('/api/notifications/delete-selected', json={'ids': [a, b]})
    assert r.status_code == 200
    with app.app_context():
        assert Notification.query.filter_by(user_id=u['id']).count() == 1


def test_delete_selected_rejects_empty(client, make_user, login):
    u = make_user(username='dsel_empty')
    _login(client, login, u)
    r = client.post('/api/notifications/delete-selected', json={'ids': []})
    assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# Push — public VAPID key + subscribe/unsubscribe
# ═══════════════════════════════════════════════════════════════
def test_vapid_public_key_anonymous(client):
    r = client.get('/api/notifications/push/vapid_public_key')
    assert r.status_code == 200
    data = r.get_json()
    assert 'public_key' in data
    assert isinstance(data['public_key'], str)
    assert len(data['public_key']) > 40


def test_push_subscribe_rejects_anonymous(client):
    r = client.post('/api/notifications/push/subscribe', json={
        'subscription': {'endpoint': 'https://x', 'keys': {'p256dh': 'a', 'auth': 'b'}}
    })
    assert r.status_code == 302


def test_push_subscribe_rejects_missing_subscription(client, make_user, login):
    u = make_user(username='ps_miss')
    _login(client, login, u)
    r = client.post('/api/notifications/push/subscribe', json={})
    assert r.status_code == 400


def test_push_subscribe_rejects_non_https_endpoint(client, make_user, login):
    u = make_user(username='ps_http')
    _login(client, login, u)
    r = client.post('/api/notifications/push/subscribe', json={
        'subscription': {
            'endpoint': 'http://insecure.example/push',
            'keys': {'p256dh': 'AAA', 'auth': 'BBB'},
        }
    })
    assert r.status_code == 400


def test_push_subscribe_rejects_oversized_p256dh(client, make_user, login):
    u = make_user(username='ps_big')
    _login(client, login, u)
    r = client.post('/api/notifications/push/subscribe', json={
        'subscription': {
            'endpoint': 'https://fcm.example/x',
            'keys': {'p256dh': 'x' * 500, 'auth': 'ok'},
        }
    })
    assert r.status_code == 400


def test_push_subscribe_success(client, app, make_user, login):
    u = make_user(username='ps_ok')
    _login(client, login, u)
    endpoint = 'https://fcm.example/sub-' + 'a' * 20
    r = client.post('/api/notifications/push/subscribe', json={
        'subscription': {
            'endpoint': endpoint,
            'keys': {'p256dh': 'PUBKEY', 'auth': 'AUTHKEY'},
        }
    })
    assert r.status_code == 201
    with app.app_context():
        sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
        assert sub is not None
        assert sub.user_id == u['id']


def test_push_subscribe_rejects_other_user_endpoint(client, app, make_user, login):
    """لا يسمح بالاستيلاء على endpoint يملكه مستخدم آخر."""
    owner = make_user(username='ps_own')
    attacker = make_user(username='ps_atk')
    with app.app_context():
        s = PushSubscription(
            user_id=owner['id'],
            endpoint='https://fcm.example/owned',
            p256dh='X', auth='Y',
        )
        db.session.add(s)
        db.session.commit()

    _login(client, login, attacker)
    r = client.post('/api/notifications/push/subscribe', json={
        'subscription': {
            'endpoint': 'https://fcm.example/owned',
            'keys': {'p256dh': 'X', 'auth': 'Y'},
        }
    })
    assert r.status_code == 409


def test_push_subscribe_same_user_updates(client, app, make_user, login):
    u = make_user(username='ps_upd')
    with app.app_context():
        s = PushSubscription(
            user_id=u['id'],
            endpoint='https://fcm.example/upd',
            p256dh='OLD', auth='OLDAUTH',
        )
        db.session.add(s)
        db.session.commit()

    _login(client, login, u)
    r = client.post('/api/notifications/push/subscribe', json={
        'subscription': {
            'endpoint': 'https://fcm.example/upd',
            'keys': {'p256dh': 'NEW', 'auth': 'NEWAUTH'},
        }
    })
    assert r.status_code == 200
    with app.app_context():
        s = PushSubscription.query.filter_by(endpoint='https://fcm.example/upd').first()
        assert s.p256dh == 'NEW'


def test_push_unsubscribe(client, app, make_user, login):
    u = make_user(username='pu_ok')
    with app.app_context():
        s = PushSubscription(
            user_id=u['id'],
            endpoint='https://fcm.example/unsub',
            p256dh='X', auth='Y',
        )
        db.session.add(s)
        db.session.commit()

    _login(client, login, u)
    r = client.post('/api/notifications/push/unsubscribe', json={
        'endpoint': 'https://fcm.example/unsub'
    })
    assert r.status_code == 200
    with app.app_context():
        assert PushSubscription.query.filter_by(endpoint='https://fcm.example/unsub').count() == 0


def test_push_unsubscribe_not_found(client, make_user, login):
    u = make_user(username='pu_nf')
    _login(client, login, u)
    r = client.post('/api/notifications/push/unsubscribe', json={
        'endpoint': 'https://fcm.example/never-existed'
    })
    assert r.status_code == 404
