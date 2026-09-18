"""
اختبارات حماية CSRF على الـ blueprints التي تستخدم Session auth.

السياسة الحالية:
  - api_bp + delivery_api_bp → CSRF معفى (JWT Bearer لا يعتمد على كوكي).
  - social_bp, reels_bp, delivery_bp → CSRF مفعّل (session auth).

طريقة العمل:
  CSRF معطّل افتراضيًا في conftest.py (لتسهيل login).
  نستخدم context manager `_csrf_enabled` لتفعيله فقط حول POST المستهدف،
  ثم نُعيد الحالة الأصلية — يمنع تسربه إلى اختبارات أخرى (app.fixture
  scope=session).
"""
from contextlib import contextmanager

from database import db


# ═══════════════════════════════════════════════════════════════
# أدوات
# ═══════════════════════════════════════════════════════════════
@contextmanager
def _csrf_enabled(app):
    """تفعيل CSRF مؤقتًا مع استعادة الحالة الأصلية عند الخروج."""
    original = app.config.get('WTF_CSRF_ENABLED', False)
    app.config['WTF_CSRF_ENABLED'] = True
    try:
        yield
    finally:
        app.config['WTF_CSRF_ENABLED'] = original


def _get_csrf_token(client, app):
    """
    استخراج CSRF token المُوقَّع من HTML.

    Flask-WTF يخزّن raw secret في session['csrf_token']، لكن القيمة التي
    يجب إرسالها في الرأس هي token موقّع (raw.timestamp.signature). هذه
    القيمة مُصيَّرة في base.html داخل:
      <meta name="csrf-token" content="{{ csrf_token }}">
    لذا نستخرجها من HTML — أضمن من قراءة session مباشرة.
    """
    import re
    from flask import url_for
    with app.test_request_context():
        market_url = url_for('market.market')
    r = client.get(market_url)
    html = r.get_data(as_text=True)
    m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    if m:
        return m.group(1)
    # fallback: من input hidden في أي نموذج
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else None


# ═══════════════════════════════════════════════════════════════
# social_bp — Reaction
# ═══════════════════════════════════════════════════════════════
def test_reaction_without_csrf_is_rejected(
    client, app, make_user, login, make_active_store, make_product
):
    u = make_user(username='csrfreaction1')
    assert login(u['username'], u['password']).status_code == 302
    s = make_active_store()
    p = make_product(s['id'])

    with _csrf_enabled(app):
        r = client.post(
            f'/api/products/{p["id"]}/reaction',
            json={'reaction_type': 'like'}
        )
    assert r.status_code == 400


def test_reaction_with_csrf_succeeds(
    client, app, make_user, login, make_active_store, make_product
):
    u = make_user(username='csrfreaction2')
    assert login(u['username'], u['password']).status_code == 302
    s = make_active_store()
    p = make_product(s['id'])

    # احصل على token من الجلسة الحالية (بعد login)
    token = _get_csrf_token(client, app)
    assert token, "CSRF token should be in session after visiting /market"

    with _csrf_enabled(app):
        r = client.post(
            f'/api/products/{p["id"]}/reaction',
            json={'reaction_type': 'like'},
            headers={'X-CSRF-Token': token}
        )
    assert r.status_code in (200, 201)


# ═══════════════════════════════════════════════════════════════
# reels_bp — Reaction / View
# ملاحظة: لا نحتاج كائن Reel حقيقي — CSRF check يحدث قبل منطق الـ view.
# ═══════════════════════════════════════════════════════════════
def test_reel_reaction_without_csrf_is_rejected(
    client, app, make_user, login
):
    u = make_user(username='csrfreel1')
    assert login(u['username'], u['password']).status_code == 302

    with _csrf_enabled(app):
        r = client.post('/api/reels/999999/reaction', json={'reaction_type': 'like'})
    assert r.status_code == 400


def test_reel_view_without_csrf_is_rejected(client, app):
    with _csrf_enabled(app):
        r = client.post('/api/reels/999999/view')
    assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# delivery_bp — HTML session routes
# ═══════════════════════════════════════════════════════════════
def test_delivery_availability_without_csrf_is_rejected(
    client, app, make_user, login
):
    u = make_user(username='csfrdelivery1', role='delivery')
    assert login(u['username'], u['password']).status_code == 302

    with _csrf_enabled(app):
        r = client.post('/delivery/availability', data={'is_available': 'true'})
    assert r.status_code == 400


def test_delivery_claim_without_csrf_is_rejected(
    client, app, make_user, login
):
    u = make_user(username='csfrdelivery2', role='delivery')
    assert login(u['username'], u['password']).status_code == 302

    with _csrf_enabled(app):
        r = client.post('/delivery/orders/999999/claim')
    assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════
# تأكيد الإعفاء الصحيح: api_bp + delivery_api_bp
# ═══════════════════════════════════════════════════════════════
def test_jwt_api_still_csrf_exempt(client, app):
    """api_bp معفى — الطلب بدون JWT يُرجع 401 (وليس 400 CSRF)."""
    with _csrf_enabled(app):
        r = client.post(
            '/api/orders',
            json={'items': [{'product_id': 1, 'quantity': 1}]},
            headers={'Content-Type': 'application/json'}
        )
    assert r.status_code == 401


def test_delivery_api_still_csrf_exempt(client, app):
    """delivery_api_bp معفى — الطلب بدون JWT يُرجع 401 (وليس 400 CSRF)."""
    with _csrf_enabled(app):
        r = client.post(
            '/api/delivery/orders/999999/claim',
            headers={'Content-Type': 'application/json'}
        )
    assert r.status_code == 401
