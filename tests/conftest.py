"""
Pytest fixtures مشتركة لكل الاختبارات.

- يتم ضبط متغيرات البيئة قبل استيراد app لضمان استخدام SQLite مؤقت.
- قاعدة البيانات تُعاد بناؤها قبل كل اختبار (drop_all + create_all).
- CSRF معطّل، rate limiting معطّل، scheduler معطّل، Cloudinary معطّل.
"""
import os
import sys
import tempfile
from datetime import timedelta

import pytest

# ── مسار المشروع على sys.path ─────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── قاعدة بيانات اختبار في مجلد مؤقت ────────────────────────
_TMP_DB_DIR = tempfile.mkdtemp(prefix='husayniyyah_tests_')
_TMP_DB_PATH = os.path.join(_TMP_DB_DIR, 'test.db')

# ── متغيرات بيئة إلزامية قبل استيراد app ────────────────────
os.environ['FLASK_ENV'] = 'testing'
os.environ['FLASK_DEBUG'] = '0'
os.environ['SCHEDULER_ENABLED'] = '0'
os.environ['SECRET_KEY'] = 'test-secret-key-' + 'a' * 48
os.environ['JWT_SECRET_KEY'] = 'test-jwt-secret-' + 'b' * 48
os.environ['DATABASE_URL'] = f'sqlite:///{_TMP_DB_PATH}'
os.environ['ADMIN_USERNAME'] = 'testadmin'
os.environ['ADMIN_EMAIL'] = 'admin@test.local'
os.environ['ADMIN_PHONE'] = '+963900000000'
os.environ['ADMIN_PASSWORD'] = 'TestAdmin123!'
os.environ.pop('CLOUDINARY_CLOUD_NAME', None)
os.environ.pop('CLOUDINARY_API_KEY', None)
os.environ.pop('CLOUDINARY_API_SECRET', None)

# ── استيراد التطبيق بعد ضبط البيئة ──────────────────────────
from app import app as _flask_app  # noqa: E402
from database import db  # noqa: E402


@pytest.fixture(scope='session')
def app():
    """تطبيق Flask مُهيأ للاختبارات."""
    _flask_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'RATELIMIT_ENABLED': False,
        'CLOUDINARY_ENABLED': False,
        'SERVER_NAME': 'localhost.localdomain',
        'PREFERRED_URL_SCHEME': 'http',
    })
    # تعطيل limiter إن كان مفعلاً
    try:
        from app import limiter
        limiter.enabled = False
    except Exception:
        pass
    yield _flask_app


@pytest.fixture(autouse=True)
def clean_db(app):
    """إعادة بناء قاعدة البيانات قبل كل اختبار."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield
        db.session.remove()


@pytest.fixture
def client(app):
    """Werkzeug test client."""
    return app.test_client()


# ═══════════════════════════════════════════════════════════════
# Fixtures لإنشاء بيانات
# ═══════════════════════════════════════════════════════════════
@pytest.fixture
def make_user(app):
    """إنشاء مستخدم. يعيد dict بمعرفاته."""
    from models import User
    from werkzeug.security import generate_password_hash
    from shared.utils import generate_public_id

    _counter = [0]

    def _make(username=None, password='TestPass123!@#', role='customer',
              is_active=True, **kwargs):
        _counter[0] += 1
        n = _counter[0]
        if username is None:
            username = f'user{n}'
        u = User(
            username=username,
            email=kwargs.get('email', f'{username}@test.local'),
            phone=kwargs.get('phone', f'+9639111111{n:02d}'),
            password_hash=generate_password_hash(password),
            role=role,
            is_active=is_active,
            public_id=generate_public_id(),
        )
        db.session.add(u)
        db.session.commit()
        return {
            'id': u.id,
            'username': u.username,
            'email': u.email,
            'phone': u.phone,
            'public_id': u.public_id,
            'role': u.role,
            'password': password,
        }
    return _make


@pytest.fixture
def make_store(app, make_user):
    """إنشاء متجر. يعيد dict."""
    from models import Store

    _counter = [0]

    def _make(owner_id=None, name=None, subscription_status='active',
              has_delivery=False, **kwargs):
        _counter[0] += 1
        n = _counter[0]
        if owner_id is None:
            owner = make_user(username=f'owner{n}', role='owner')
            owner_id = owner['id']
        if name is None:
            name = f'Store{n}'
        s = Store(
            owner_id=owner_id,
            name=name,
            subscription_status=subscription_status,
            has_delivery=has_delivery,
            latitude=kwargs.get('latitude', 33.5),
            longitude=kwargs.get('longitude', 36.3),
            working_hours=kwargs.get('working_hours'),
        )
        db.session.add(s)
        db.session.commit()
        return {
            'id': s.id,
            'name': s.name,
            'owner_id': s.owner_id,
            'has_delivery': s.has_delivery,
        }
    return _make


@pytest.fixture
def make_active_store(app, make_store):
    """متجر مع اشتراك paid ساري — يجتاز is_store_active()."""
    from models import Store, Subscription
    from shared.time_utils import current_time

    def _make(**kwargs):
        s = make_store(**kwargs)
        sub = Subscription(
            user_id=s['owner_id'],
            store_id=s['id'],
            start_date=current_time(),
            end_date=current_time() + timedelta(days=30),
            amount=500.0,
            status='paid',
            duration_days=30,
        )
        db.session.add(sub)
        db.session.commit()
        store = db.session.get(Store, s['id'])
        store.subscription_expiry = sub.end_date
        db.session.commit()
        return s
    return _make


@pytest.fixture
def make_product(app):
    """إنشاء منتج. حقول اختيارية لتجنب الاعتماد على تفاصيل Product."""
    from models import Product

    _counter = [0]

    def _make(store_id, name=None, price=100.0, stock=10,
              is_offer=False, hide_price=False, **kwargs):
        _counter[0] += 1
        n = _counter[0]
        if name is None:
            name = f'Product{n}'
        p = Product(
            store_id=store_id,
            name=name,
            price=price,
            stock_quantity=stock,
            is_offer=is_offer,
            hide_price=hide_price,
        )
        db.session.add(p)
        db.session.commit()
        return {
            'id': p.id,
            'name': p.name,
            'price': p.price,
            'stock': p.stock_quantity,
            'store_id': p.store_id,
        }
    return _make


@pytest.fixture
def login(client):
    """دخول مستخدم. يعيد response."""
    def _login(login_id, password, **kwargs):
        return client.post(
            '/login',
            data={'login_id': login_id, 'password': password},
            follow_redirects=False,
            **kwargs
        )
    return _login
