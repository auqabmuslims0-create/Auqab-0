"""اختبارات مسارات المصادقة."""
from werkzeug.security import generate_password_hash, check_password_hash
from database import db
from models import User, PasswordReset
from shared.security import decrypt_session_secret


# ═══════════════════════════════════════════════════════════════
# التسجيل — 3 خطوات
# ═══════════════════════════════════════════════════════════════
def test_register_step1_stores_session_data(client):
    r = client.post('/register?step=1', data={
        'step': '1',
        'username': 'newuser',
        'email': 'new@test.local',
        'phone': '911111111',
    })
    assert r.status_code == 302
    assert 'step=2' in r.headers['Location']
    with client.session_transaction() as sess:
        assert sess['reg_data']['username'] == 'newuser'
        assert sess['reg_data']['email'] == 'new@test.local'
        assert sess['reg_data']['phone'] == '+963911111111'


def test_register_step1_rejects_duplicate_username(client, make_user):
    make_user(username='taken', email='taken@test.local')
    r = client.post('/register?step=1', data={
        'step': '1',
        'username': 'taken',
        'email': 'other@test.local',
        'phone': '922222222',
    })
    assert r.status_code == 302
    assert 'step=1' in r.headers['Location']


def test_register_step1_rejects_invalid_email(client):
    r = client.post('/register?step=1', data={
        'step': '1',
        'username': 'x',
        'email': 'not-an-email',
        'phone': '911111111',
    })
    assert r.status_code == 302
    assert 'step=1' in r.headers['Location']


def test_register_step2_encrypts_password_hash_in_session(client):
    client.post('/register?step=1', data={
        'step': '1', 'username': 'alice',
        'email': 'alice@test.local', 'phone': '933333333',
    })
    r = client.post('/register?step=2', data={
        'step': '2',
        'password': 'StrongPass123!@#',
        'confirm_password': 'StrongPass123!@#',
        'role': 'customer',
        'agree': 'on',
    })
    assert r.status_code == 302
    with client.session_transaction() as sess:
        stored = sess['reg_data']['password_hash']
        # يجب ألا تكون plaintext werkzeug hash
        assert not stored.startswith('scrypt:')
        assert not stored.startswith('pbkdf2:')
        # يجب أن تُفك بنجاح
        decrypted = decrypt_session_secret(stored)
        assert decrypted is not None
        assert decrypted.startswith('scrypt:') or decrypted.startswith('pbkdf2:')


def test_register_step2_rejects_weak_password(client):
    client.post('/register?step=1', data={
        'step': '1', 'username': 'bob',
        'email': 'bob@test.local', 'phone': '944444444',
    })
    r = client.post('/register?step=2', data={
        'step': '2',
        'password': '123',
        'confirm_password': '123',
        'role': 'customer',
        'agree': 'on',
    })
    assert r.status_code == 302
    assert 'step=2' in r.headers['Location']


def test_register_full_flow_creates_user(client, app):
    client.post('/register?step=1', data={
        'step': '1', 'username': 'charlie',
        'email': 'charlie@test.local', 'phone': '955555555',
    })
    client.post('/register?step=2', data={
        'step': '2',
        'password': 'StrongPass123!@#',
        'confirm_password': 'StrongPass123!@#',
        'role': 'customer',
        'agree': 'on',
    })
    r = client.post('/register?step=3', data={
        'step': '3',
        'bio': 'hello',
    })
    assert r.status_code == 302
    with app.app_context():
        u = User.query.filter_by(username='charlie').first()
        assert u is not None
        assert u.email == 'charlie@test.local'
        assert u.phone == '+963955555555'
        assert u.role == 'customer'
        assert check_password_hash(u.password_hash, 'StrongPass123!@#')


# ═══════════════════════════════════════════════════════════════
# تسجيل الدخول
# ═══════════════════════════════════════════════════════════════
def test_login_success(client, make_user):
    u = make_user(username='dave', password='MyPass123!@#')
    r = client.post('/login', data={
        'login_id': 'dave',
        'password': 'MyPass123!@#',
    })
    assert r.status_code == 302
    with client.session_transaction() as sess:
        assert sess['user_id'] == u['id']
        assert sess['role'] == 'customer'


def test_login_with_email(client, make_user):
    u = make_user(username='eve', password='MyPass123!@#',
                  email='eve@special.local')
    r = client.post('/login', data={
        'login_id': 'eve@special.local',
        'password': 'MyPass123!@#',
    })
    assert r.status_code == 302
    with client.session_transaction() as sess:
        assert sess['user_id'] == u['id']


def test_login_wrong_password(client, make_user):
    make_user(username='frank', password='Correct123!@#')
    r = client.post('/login', data={
        'login_id': 'frank',
        'password': 'Wrong123!@#',
    })
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'بيانات الدخول غير صحيحة' in body
    with client.session_transaction() as sess:
        assert 'user_id' not in sess


def test_login_rejects_inactive_user(client, make_user):
    make_user(username='banned', password='MyPass123!@#', is_active=False)
    r = client.post('/login', data={
        'login_id': 'banned',
        'password': 'MyPass123!@#',
    })
    assert r.status_code == 200
    assert 'الحساب محظور' in r.get_data(as_text=True)
    with client.session_transaction() as sess:
        assert 'user_id' not in sess


def test_login_rate_limit_blocks_6th_attempt(client, make_user):
    make_user(username='victim', password='Correct123!@#')
    # 5 محاولات فاشلة
    for _ in range(5):
        client.post('/login', data={
            'login_id': 'victim',
            'password': 'Wrong123!@#',
        })
    # المحاولة السادسة بكلمة المرور الصحيحة — يجب أن تُرفض
    r = client.post('/login', data={
        'login_id': 'victim',
        'password': 'Correct123!@#',
    }, follow_redirects=False)
    assert r.status_code == 200
    assert 'تجاوز عدد المحاولات' in r.get_data(as_text=True)


def test_login_clears_previous_session(client, make_user):
    """منع session fixation."""
    u = make_user(username='grace', password='MyPass123!@#')
    with client.session_transaction() as sess:
        sess['pre_login_marker'] = 'should_be_cleared'
    client.post('/login', data={
        'login_id': 'grace',
        'password': 'MyPass123!@#',
    })
    with client.session_transaction() as sess:
        assert 'pre_login_marker' not in sess
        assert sess['user_id'] == u['id']


def test_logout_clears_session(client, make_user, login):
    u = make_user(username='henry', password='MyPass123!@#')
    login('henry', 'MyPass123!@#')
    r = client.post('/logout')
    assert r.status_code == 302
    with client.session_transaction() as sess:
        assert 'user_id' not in sess


def test_logout_via_get_is_rejected(client, make_user, login):
    """GET /logout يجب أن يُرفض بـ 405 — منع CSRF logout (<img src=/logout>)."""
    u = make_user(username='logout_get', password='MyPass123!@#')
    login('logout_get', 'MyPass123!@#')
    r = client.get('/logout')
    assert r.status_code == 405
    # الجلسة لا تزال نشطة
    with client.session_transaction() as sess:
        assert sess.get('user_id') == u['id']


def test_logout_via_post_succeeds(client, make_user, login):
    """POST /logout يمسح الجلسة."""
    u = make_user(username='logout_post', password='MyPass123!@#')
    login('logout_post', 'MyPass123!@#')
    r = client.post('/logout')
    assert r.status_code == 302
    with client.session_transaction() as sess:
        assert 'user_id' not in sess


# ═══════════════════════════════════════════════════════════════
# استعادة كلمة المرور
# ═══════════════════════════════════════════════════════════════
def test_forgot_password_creates_session_for_existing_user(client, make_user):
    u = make_user(username='ivan', email='ivan@test.local')
    r = client.post('/forgot_password', data={'email': 'ivan@test.local'})
    assert r.status_code == 302
    assert 'confirm_identity' in r.headers['Location']
    with client.session_transaction() as sess:
        assert sess.get('reset_email') == 'ivan@test.local'


def test_forgot_password_does_not_reveal_nonexistent_email(client):
    r = client.post('/forgot_password', data={'email': 'nobody@nowhere.local'})
    # يجب أن يعيد التوجيه لصفحة login بنفس رسالة "if exists"
    assert r.status_code == 302
    assert 'login' in r.headers['Location']


def test_password_reset_full_flow(client, app, make_user):
    u = make_user(username='jane', email='jane@test.local',
                  phone='+963966666666')
    # 1) forgot password
    client.post('/forgot_password', data={'email': 'jane@test.local'})
    # 2) confirm identity (phone بدون +963)
    r = client.post('/confirm_identity', data={
        'username': u['username'],
        'phone': u['phone'].replace('+963', ''),
        'public_id': u['public_id'],
        'role': u['role'],
    })
    assert r.status_code == 302
    location = r.headers['Location']
    assert '/reset_password/' in location
    token = location.rsplit('/', 1)[-1].split('?')[0]
    assert token
    # 3) reset password
    r = client.post(f'/reset_password/{token}', data={
        'password': 'NewStrong456!@#',
        'confirm_password': 'NewStrong456!@#',
    })
    assert r.status_code == 302
    # 4) verify password changed
    with app.app_context():
        user = db.session.get(User, u['id'])
        assert check_password_hash(user.password_hash, 'NewStrong456!@#')
        # Token must be consumed
        assert PasswordReset.query.filter_by(user_id=u['id']).first() is None


def test_password_reset_rejects_wrong_identity(client, make_user):
    make_user(username='kate', email='kate@test.local',
              phone='+963977777777')
    client.post('/forgot_password', data={'email': 'kate@test.local'})
    r = client.post('/confirm_identity', data={
        'username': 'kate',
        'phone': '900000000',  # خطأ
        'public_id': 'wrong-id',
        'role': 'customer',
    })
    assert r.status_code == 302
    # يعيد إلى confirm_identity وليس reset_password
    assert 'reset_password' not in r.headers['Location']


def test_password_reset_rejects_invalid_token(client):
    r = client.get('/reset_password/invalidtoken123')
    assert r.status_code == 302
    assert 'forgot_password' in r.headers['Location']


# ═══════════════════════════════════════════════════════════════
# حماية decorators
# ═══════════════════════════════════════════════════════════════
def test_unauthenticated_redirect_to_login(client):
    r = client.get('/cart')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_admin_route_requires_admin_role(client, app, make_user, login):
    """مستخدم عادي لا يصل لصفحات admin (يجب أن يُرفض بـ 403)."""
    make_user(username='normal', password='MyPass123!@#', role='customer')
    login('normal', 'MyPass123!@#')
    with app.test_request_context():
        from flask import url_for
        admin_url = url_for('admin.admin_dashboard')
    r = client.get(admin_url)
    assert r.status_code == 403


def test_owner_cannot_access_admin_dashboard(client, app, make_user, login):
    """صاحب متجر أيضًا لا يصل لصفحات admin."""
    make_user(username='owneruser', password='MyPass123!@#', role='owner')
    login('owneruser', 'MyPass123!@#')
    with app.test_request_context():
        from flask import url_for
        admin_url = url_for('admin.admin_dashboard')
    r = client.get(admin_url)
    assert r.status_code == 403


def test_admin_can_access_admin_dashboard(client, app, make_user, login):
    """المدير يصل بنجاح (تحقق إيجابي — ليس فقط سلبي)."""
    make_user(username='realdmin', password='MyPass123!@#', role='admin')
    login('realdmin', 'MyPass123!@#')
    with app.test_request_context():
        from flask import url_for
        admin_url = url_for('admin.admin_dashboard')
    r = client.get(admin_url)
    assert r.status_code == 200
