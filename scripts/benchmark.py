"""
Benchmark — يقيس زمن استجابة المسارات الحرجة + عدد استعلامات SQL لكل طلب.

الاستخدام:
    python scripts/benchmark.py                    # scale=100 (100 متجر)
    python scripts/benchmark.py --scale 50         # أصغر، أسرع
    python scripts/benchmark.py --iter 5           # 5 طلبات/مسار

يستخدم DB مؤقتة في /tmp — لا يلمس husayniyyah.db ولا test.db.
"""
import argparse
import os
import statistics
import sys
import tempfile
import time

# ─── env setup قبل استيراد app ───
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

_TMP_DIR = tempfile.mkdtemp(prefix='husayniyyah_bench_')
_TMP_DB = os.path.join(_TMP_DIR, 'bench.db')

os.environ['FLASK_ENV'] = 'testing'
os.environ['SCHEDULER_ENABLED'] = '0'
os.environ['SECRET_KEY'] = 'bench-secret-' + 'a' * 48
os.environ['JWT_SECRET_KEY'] = 'bench-jwt-' + 'b' * 48
os.environ['DATABASE_URL'] = f'sqlite:///{_TMP_DB}'
os.environ['PUSH_ENABLED'] = '0'

# ─── imports بعد ضبط env ───
from werkzeug.security import generate_password_hash  # noqa: E402
from sqlalchemy import event  # noqa: E402
from database import db  # noqa: E402
from app import app  # noqa: E402
from models import (  # noqa: E402
    User, Store, Product, Category, Order, OrderItem,
    Subscription, Notification, Reel,
)
from shared.time_utils import current_time  # noqa: E402
from datetime import timedelta  # noqa: E402


# ═══════════════════════════════════════════════════════════════
# SQL query counter
# ═══════════════════════════════════════════════════════════════
_QUERY_COUNT = [0]


def _install_sql_counter():
    engine = db.engine

    @event.listens_for(engine, "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):
        _QUERY_COUNT[0] += 1


def _reset_sql_counter():
    _QUERY_COUNT[0] = 0


# ═══════════════════════════════════════════════════════════════
# Seeding
# ═══════════════════════════════════════════════════════════════
_PASSWORD_HASH = None  # lazy


def _hash():
    global _PASSWORD_HASH
    if _PASSWORD_HASH is None:
        # pbkdf2 مع iterations قليلة لتفادي انتظار scrypt في الإعداد
        _PASSWORD_HASH = generate_password_hash(
            'BenchPass123!@#', method='pbkdf2:sha256:1000'
        )
    return _PASSWORD_HASH


def seed_data(scale):
    """scale = عدد المتاجر. المنتجات = scale * 10، الطلبات = scale * 5."""
    print(f'Seeding: {scale} stores × 10 products = {scale * 10} products ...')
    t0 = time.perf_counter()

    with app.app_context():
        db.drop_all()
        db.create_all()

        pw = _hash()

        admin = User(username='bench_admin', email='admin@bench.local',
                     phone='+963911000000', password_hash=pw, role='admin',
                     is_active=True, public_id='B-AAAA-0001')
        customer = User(username='bench_customer', email='customer@bench.local',
                        phone='+963911000001', password_hash=pw, role='customer',
                        is_active=True, public_id='B-AAAA-0002')
        owner = User(username='bench_owner', email='owner@bench.local',
                     phone='+963911000002', password_hash=pw, role='owner',
                     is_active=True, public_id='B-AAAA-0003')
        driver = User(username='bench_driver', email='driver@bench.local',
                      phone='+963911000003', password_hash=pw, role='delivery',
                      is_active=True, is_available=True, max_active_orders=10,
                      public_id='B-AAAA-0004')
        db.session.add_all([admin, customer, owner, driver])
        db.session.commit()

        # stores + products + subscriptions + categories
        now = current_time()
        end = now + timedelta(days=30)
        for i in range(scale):
            store = Store(
                owner_id=owner.id, name=f'Store{i:04d}',
                subscription_status='active', has_delivery=(i % 3 == 0),
                latitude=33.5 + i * 0.001, longitude=36.3 + i * 0.001,
            )
            db.session.add(store)
            db.session.flush()

            db.session.add(Subscription(
                user_id=owner.id, store_id=store.id,
                start_date=now, end_date=end,
                amount=500.0, status='paid', duration_days=30,
            ))
            db.session.add(Category(name=f'Cat{i:04d}', store_id=store.id))
            for j in range(10):
                db.session.add(Product(
                    store_id=store.id, name=f'Product {i}-{j}',
                    price=100.0 + j, stock_quantity=50,
                    is_offer=(j % 5 == 0),
                ))
        db.session.commit()

        # orders (delivered mostly, some new)
        stores = Store.query.limit(scale).all()
        products = {}
        for s in stores[:min(20, scale)]:
            p = Product.query.filter_by(store_id=s.id).first()
            if p:
                products[s.id] = p

        for i in range(scale * 5):
            s = stores[i % len(stores)]
            p = products.get(s.id)
            if not p:
                p = Product.query.filter_by(store_id=s.id).first()
                if p:
                    products[s.id] = p
            if not p:
                continue
            status = 'delivered' if i % 3 != 0 else 'new'
            o = Order(
                customer_id=customer.id, store_id=s.id,
                status=status, total=100.0,
                delivery_fee=0.0 if not s.has_delivery else 100.0,
            )
            db.session.add(o)
            db.session.flush()
            db.session.add(OrderItem(
                order_id=o.id, product_id=p.id, quantity=1, price=100.0,
            ))
        db.session.commit()

        # notifications for customer (poll test)
        for i in range(50):
            db.session.add(Notification(
                user_id=customer.id, title=f'N{i}',
                message=f'Message {i}', type='info', is_read=(i % 2 == 0),
            ))
        db.session.commit()

        # reels
        for s in stores[:min(20, scale)]:
            for _ in range(2):
                db.session.add(Reel(
                    store_id=s.id, video_url='x.mp4',
                    caption='r', is_active=True, views=10,
                ))
        db.session.commit()

    print(f'  Seeded in {time.perf_counter() - t0:.2f}s')
    return {
        'admin': admin.id if False else None,  # dummy
        'customer': None,  # filled below
    }


# ═══════════════════════════════════════════════════════════════
# Login + benchmark
# ═══════════════════════════════════════════════════════════════
_CREDS = {
    'admin':    ('bench_admin', 'BenchPass123!@#'),
    'customer': ('bench_customer', 'BenchPass123!@#'),
    'owner':    ('bench_owner', 'BenchPass123!@#'),
    'delivery': ('bench_driver', 'BenchPass123!@#'),
}


def _login(client, role):
    # /logout أصبح POST-only (منع CSRF logout). GET يُرجع 405 ولا يمسح الجلسة.
    client.post('/logout')
    r = client.post('/login', data={
        'login_id': _CREDS[role][0],
        'password': _CREDS[role][1],
    })
    assert r.status_code == 302, f'login failed for {role}: {r.status_code}'
    # تحقق أن الدور صحيح فعلاً
    with client.session_transaction() as sess:
        actual_role = sess.get('role')
    assert actual_role == role, (
        f'role mismatch: expected {role}, session has {actual_role}'
    )


def bench(client, method, path, n=10, role=None):
    if role is not None:
        _login(client, role)
    else:
        client.post('/logout')

    # Warmup: طلب واحد خارج القياس (cold start: Jinja compile, engine, imports)
    client.open(path, method=method, follow_redirects=False)

    times = []
    queries = []
    last_status = None
    for _ in range(n):
        _reset_sql_counter()
        t0 = time.perf_counter()
        r = client.open(path, method=method, follow_redirects=False)
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)
        queries.append(_QUERY_COUNT[0])
        last_status = r.status_code

    return {
        'path': path,
        'method': method,
        'role': role or 'anon',
        'status': last_status,
        'avg_ms': statistics.mean(times),
        'p50_ms': statistics.median(times),
        'max_ms': max(times),
        'queries': statistics.mean(queries),
    }


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scale', type=int, default=100,
                    help='عدد المتاجر (default: 100)')
    ap.add_argument('--iter', type=int, default=10,
                    help='عدد الطلبات لكل مسار (default: 10)')
    args = ap.parse_args()

    app.config['WTF_CSRF_ENABLED'] = False
    app.config['RATELIMIT_ENABLED'] = False
    try:
        from app import limiter
        limiter.enabled = False
    except Exception:
        pass

    with app.app_context():
        _install_sql_counter()

    seed_data(args.scale)

    # Find a valid store id
    with app.app_context():
        first_store = Store.query.first()
        first_product = Product.query.first()
        sid = first_store.id if first_store else 1
        pid = first_product.id if first_product else 1

    client = app.test_client()

    tests = [
        ('GET', '/market', None),
        ('GET', '/market?sort=newest', None),
        ('GET', '/market?sort=price_asc', None),
        ('GET', '/market?sort=reviews', None),
        ('GET', '/stores', None),
        ('GET', f'/stores/{sid}', None),
        ('GET', f'/stores/{sid}/products', None),
        ('GET', f'/product/{pid}', None),
        ('GET', '/offers', None),
        ('GET', '/reels', None),
        ('GET', '/cart', 'customer'),
        ('GET', '/notifications', 'customer'),
        ('GET', '/api/notifications', 'customer'),
        ('GET', '/api/updates', 'customer'),
        ('GET', '/api/updates', 'owner'),
        ('GET', '/api/updates', 'admin'),
        ('GET', '/api/updates', 'delivery'),
        ('GET', '/delivery', 'delivery'),
        ('GET', '/my_stores', 'owner'),
        ('GET', f'/store/{sid}/orders', 'owner'),
        ('GET', f'/store/{sid}/products', 'owner'),
        ('GET', '/store/stats', 'owner'),
        ('GET', '/admin', 'admin'),
        ('GET', '/admin/users', 'admin'),
        ('GET', '/admin/orders', 'admin'),
        ('GET', '/admin/stores', 'admin'),
        ('GET', '/admin/subscriptions', 'admin'),
        ('GET', '/admin/finance', 'admin'),
        ('GET', '/admin/payments', 'admin'),
    ]

    print(f'\nRunning {len(tests)} endpoints × {args.iter} iterations ...\n')

    results = []
    for method, path, role in tests:
        try:
            res = bench(client, method, path, n=args.iter, role=role)
            results.append(res)
            print(f'  [{res["status"]}] {res["role"]:8s} {res["path"]:40s} '
                  f'avg={res["avg_ms"]:6.1f}ms  '
                  f'q={res["queries"]:5.1f}')
        except Exception as e:
            print(f'  [ERR] {role} {path}: {type(e).__name__}: {e}')

    # Sorted by avg_ms
    print('\n' + '=' * 90)
    print('Top 10 SLOWEST (avg_ms):')
    print('=' * 90)
    for r in sorted(results, key=lambda x: -x['avg_ms'])[:10]:
        print(f'  {r["avg_ms"]:7.1f} ms   q={r["queries"]:5.1f}   '
              f'{r["role"]:8s} {r["path"]}')

    print('\n' + '=' * 90)
    print('Top 10 HIGHEST query count (N+1 detection):')
    print('=' * 90)
    for r in sorted(results, key=lambda x: -x['queries'])[:10]:
        print(f'  q={r["queries"]:6.1f}   {r["avg_ms"]:7.1f} ms   '
              f'{r["role"]:8s} {r["path"]}')

    # Cleanup
    try:
        os.remove(_TMP_DB)
    except Exception:
        pass

    print(f'\nDone.')


if __name__ == '__main__':
    main()
