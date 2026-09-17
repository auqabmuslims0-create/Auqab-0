"""اختبارات الاشتراكات: submit, verify, approve, expire."""
from datetime import timedelta
from database import db
from models import Store, Subscription, User
from shared.services.subscription_service import SubscriptionService
from shared.time_utils import current_time


# ═══════════════════════════════════════════════════════════════
# submit_subscription_request
# ═══════════════════════════════════════════════════════════════
def test_submit_subscription_creates_pending(app, make_user, make_store):
    with app.app_context():
        u = make_user(username='owner1', role='owner')
        s = make_store(owner_id=u['id'], subscription_status='pending')
        user = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        ok, msg, sub = SubscriptionService.submit_subscription_request(
            user, store, payment_method='manual_delivery'
        )
        assert ok is True, msg
        assert sub is not None
        assert sub.status == 'pending'
        assert sub.store_id == store.id


def test_submit_subscription_idempotent(app, make_user, make_store):
    with app.app_context():
        u = make_user(username='owner2', role='owner')
        s = make_store(owner_id=u['id'], subscription_status='pending')
        user = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        ok1, _, sub1 = SubscriptionService.submit_subscription_request(
            user, store, payment_method='manual_delivery'
        )
        ok2, _, sub2 = SubscriptionService.submit_subscription_request(
            user, store, payment_method='manual_delivery'
        )
        assert ok1 and ok2
        assert sub1.id == sub2.id  # نفس الصف، لا إنشاء مكرر


def test_submit_subscription_denies_other_owner(app, make_user, make_store):
    with app.app_context():
        owner = make_user(username='owner3', role='owner')
        other = make_user(username='intruder')
        s = make_store(owner_id=owner['id'])
        other_user = db.session.get(User, other['id'])
        store = db.session.get(Store, s['id'])
        ok, msg, sub = SubscriptionService.submit_subscription_request(
            other_user, store, payment_method='manual_delivery'
        )
        assert ok is False
        assert 'غير مسموح' in msg


# ═══════════════════════════════════════════════════════════════
# verify_manual_confirmation
# ═══════════════════════════════════════════════════════════════
def test_verify_manual_confirmation_wrong_code(app, make_user, make_store):
    with app.app_context():
        u = make_user(username='owner4', role='owner')
        s = make_store(owner_id=u['id'], subscription_status='pending')
        user = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        _, _, sub = SubscriptionService.submit_subscription_request(
            user, store, payment_method='manual_delivery'
        )
        ok, msg = SubscriptionService.verify_manual_confirmation(
            user, sub.id, '000000'
        )
        assert ok is False
        assert 'غير صحيح' in msg
        db.session.refresh(sub)
        assert sub.confirmation_attempts == 1


def test_verify_manual_confirmation_success(app, make_user, make_store):
    with app.app_context():
        u = make_user(username='owner5', role='owner')
        s = make_store(owner_id=u['id'], subscription_status='pending')
        user = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        _, _, sub = SubscriptionService.submit_subscription_request(
            user, store, payment_method='manual_delivery'
        )
        # نقرأ الكود المُخزَّن مباشرة
        code = sub.confirmation_code
        assert code is not None
        ok, msg = SubscriptionService.verify_manual_confirmation(user, sub.id, code)
        assert ok is True, msg
        db.session.refresh(sub)
        assert sub.status == 'paid'
        db.session.refresh(store)
        assert store.subscription_status == 'active'


def test_verify_manual_confirmation_rejects_other_user(app, make_user, make_store):
    with app.app_context():
        owner = make_user(username='owner6', role='owner')
        other = make_user(username='other6')
        s = make_store(owner_id=owner['id'])
        owner_user = db.session.get(User, owner['id'])
        other_user = db.session.get(User, other['id'])
        store = db.session.get(Store, s['id'])
        _, _, sub = SubscriptionService.submit_subscription_request(
            owner_user, store, payment_method='manual_delivery'
        )
        ok, msg = SubscriptionService.verify_manual_confirmation(
            other_user, sub.id, sub.confirmation_code
        )
        assert ok is False
        assert 'غير مسموح' in msg


# ═══════════════════════════════════════════════════════════════
# approve / reject
# ═══════════════════════════════════════════════════════════════
def test_approve_subscription_activates(app, make_user, make_store):
    with app.app_context():
        u = make_user(username='owner7', role='owner')
        s = make_store(owner_id=u['id'], subscription_status='pending')
        owner = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        _, _, sub = SubscriptionService.submit_subscription_request(
            owner, store, payment_method='manual_delivery'
        )
        ok, msg = SubscriptionService.approve_subscription(sub.id)
        assert ok is True, msg
        db.session.refresh(sub)
        db.session.refresh(store)
        assert sub.status == 'paid'
        assert store.subscription_status == 'active'
        assert store.subscription_expiry == sub.end_date


def test_reject_subscription_marks_cancelled(app, make_user, make_store):
    with app.app_context():
        u = make_user(username='owner8', role='owner')
        s = make_store(owner_id=u['id'], subscription_status='pending')
        owner = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        _, _, sub = SubscriptionService.submit_subscription_request(
            owner, store, payment_method='manual_delivery'
        )
        ok, msg = SubscriptionService.reject_subscription(sub.id, admin_note='test')
        assert ok is True, msg
        db.session.refresh(sub)
        db.session.refresh(store)
        assert sub.status == 'cancelled'
        assert store.subscription_status == 'cancelled'


# ═══════════════════════════════════════════════════════════════
# extend
# ═══════════════════════════════════════════════════════════════
def test_extend_subscription_extends_end_date(app, make_user, make_store):
    with app.app_context():
        u = make_user(username='owner9', role='owner')
        s = make_store(owner_id=u['id'], subscription_status='active')
        owner = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        _, _, sub = SubscriptionService.submit_subscription_request(
            owner, store, payment_method='manual_delivery'
        )
        SubscriptionService.approve_subscription(sub.id)
        db.session.refresh(sub)
        original_end = sub.end_date
        ok, msg = SubscriptionService.extend_subscription(sub.id, days=15)
        assert ok is True, msg
        db.session.refresh(sub)
        assert sub.end_date == original_end + timedelta(days=15)


# ═══════════════════════════════════════════════════════════════
# expire_subscriptions
# ═══════════════════════════════════════════════════════════════
def test_expire_subscriptions_marks_expired(app, make_user, make_store):
    with app.app_context():
        u = make_user(username='owner10', role='owner')
        s = make_store(owner_id=u['id'], subscription_status='active')
        owner = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        # اشتراك منتهي مسبقاً
        sub = Subscription(
            user_id=owner.id,
            store_id=store.id,
            start_date=current_time() - timedelta(days=60),
            end_date=current_time() - timedelta(days=1),
            amount=500.0,
            status='paid',
            duration_days=30,
        )
        db.session.add(sub)
        db.session.commit()
        count = SubscriptionService.expire_subscriptions()
        assert count >= 1
        db.session.refresh(sub)
        db.session.refresh(store)
        assert sub.status == 'expired'
        assert store.subscription_status == 'expired'


def test_expire_respects_grace_days(app, make_user, make_store):
    with app.app_context():
        u = make_user(username='owner11', role='owner')
        s = make_store(owner_id=u['id'], subscription_status='active')
        owner = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        store.subscription_grace_days = 7
        db.session.add(store)
        # انتهى منذ يوم — لكن داخل فترة السماح
        sub = Subscription(
            user_id=owner.id,
            store_id=store.id,
            start_date=current_time() - timedelta(days=31),
            end_date=current_time() - timedelta(days=1),
            amount=500.0,
            status='paid',
            duration_days=30,
        )
        db.session.add(sub)
        db.session.commit()
        SubscriptionService.expire_subscriptions()
        db.session.refresh(sub)
        # يجب أن يبقى paid (لم ينته فعلياً بسبب grace)
        assert sub.status == 'paid'


def test_expire_with_auto_renew_creates_pending(app, make_user, make_store):
    with app.app_context():
        u = make_user(username='owner12', role='owner')
        s = make_store(owner_id=u['id'], subscription_status='active')
        owner = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        store.auto_renew = True
        db.session.add(store)
        sub = Subscription(
            user_id=owner.id,
            store_id=store.id,
            start_date=current_time() - timedelta(days=31),
            end_date=current_time() - timedelta(days=1),
            amount=500.0,
            status='paid',
            duration_days=30,
        )
        db.session.add(sub)
        db.session.commit()
        count = SubscriptionService.expire_subscriptions()
        assert count >= 1
        db.session.refresh(sub)
        assert sub.status == 'expired'
        # يجب إنشاء اشتراك pending جديد
        pending = Subscription.query.filter_by(
            store_id=store.id, status='pending'
        ).first()
        assert pending is not None
        db.session.refresh(store)
        assert store.subscription_status == 'pending'


# ═══════════════════════════════════════════════════════════════
# I1 regression: تأكيد الاشتراك لا يؤثر على تسجيل الدخول
# ═══════════════════════════════════════════════════════════════
def test_verify_manual_confirmation_does_not_affect_login(
    client, app, make_user, login, make_store
):
    """
    خطأ في كود تأكيد الاشتراك 5 مرات يجب ألا يقفل تسجيل الدخول.

    هذا اختبار regression: قبل الإصلاح، كان verify_manual_confirmation
    يستخدم login_attempts، فأي خطأ في التأكيد يُحسب على login ويقفل
    IP لمدة 5 دقائق.
    """
    # مستخدم + متجر + اشتراك pending
    u = make_user(username='isolated', password='MyPass123!@#', role='owner')
    s = make_store(owner_id=u['id'], subscription_status='pending')
    assert login(u['username'], u['password']).status_code == 302

    with app.app_context():
        owner = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        _, _, sub = SubscriptionService.submit_subscription_request(
            owner, store, payment_method='manual_delivery'
        )
        sub_id = sub.id

    # 5 محاولات فاشلة في confirm_identity / verify_manual_confirmation
    # نستخدم verify_manual_confirmation مباشرة عبر الخدمة
    with app.app_context():
        owner = db.session.get(User, u['id'])
        for _ in range(5):
            SubscriptionService.verify_manual_confirmation(owner, sub_id, '000000')

    # الآن يجب أن يتمكن المستخدم من تسجيل الخروج والدخول مجددًا بنجاح
    client.get('/logout')
    r = client.post('/login', data={
        'login_id': u['username'],
        'password': u['password'],
    })
    assert r.status_code == 302
    with client.session_transaction() as sess:
        assert sess['user_id'] == u['id']


def test_verify_manual_confirmation_rate_limited_by_ip(
    client, app, make_user, make_store
):
    """
    تجاوز 10 محاولات تأكيد من نفس IP خلال 15 دقيقة → رفض.

    نتحقق مباشرة عبر الخدمة (بدون HTTP) لتجنب تعقيدات جلسة الاستعادة.
    """
    with app.app_context():
        u = make_user(username='ratelimited', role='owner')
        s = make_store(owner_id=u['id'], subscription_status='pending')
        owner = db.session.get(User, u['id'])
        store = db.session.get(Store, s['id'])
        _, _, sub = SubscriptionService.submit_subscription_request(
            owner, store, payment_method='manual_delivery'
        )
        sub_id = sub.id

    # استيراد الدالة الداخلية لتصفير العدّاد
    from shared.services.subscription_service import _sub_verify_attempts
    _sub_verify_attempts.clear()

    # 10 محاولات → يجب أن تمر (كلها فاشلة بكود خاطئ، لكن الـ IP مسموح)
    results = []
    with app.app_context():
        owner = db.session.get(User, u['id'])
        for i in range(10):
            ok, msg = SubscriptionService.verify_manual_confirmation(
                owner, sub_id, '000000'
            )
            results.append(ok)

    # كل الـ 10 الأولى: False (كود خاطئ أو sub attempt limit)
    assert all(r is False for r in results), results

    # المحاولة الـ 11 من نفس IP → يجب أن تُرفض بسبب IP rate limit
    with app.app_context():
        owner = db.session.get(User, u['id'])
        ok, msg = SubscriptionService.verify_manual_confirmation(
            owner, sub_id, '000000'
        )
    assert ok is False
    assert 'من هذا الجهاز' in msg
