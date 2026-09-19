# Architecture — سوق الحسينية

## نظرة عامة

سوق إلكتروني متعدد المتاجر — منصة وسيطة تربط:
- أصحاب المتاجر (owner) الذين يديرون متاجرهم باشتراك دوري.
- الزبائن (customer) الذين يتصفحون المنتجات ويطلبونها.
- مندوبي التوصيل (delivery) الذين يستلمون ويوصلون الطلبات.
- المديرين (admin) الذين يديرون المنصة كاملة.

## Stack التقني

- Backend: Flask 3.x + Python 3.11
- ORM: SQLAlchemy 2.x + Flask-Migrate (Alembic)
- DB: PostgreSQL (prod) / SQLite (dev/test)
- Auth: Sessions (web) + JWT (mobile API)
- Frontend: Jinja2 + Bootstrap 5 + vanilla JS
- PWA: Service Worker + manifest + offline.html
- Media: Cloudinary (prod) / local (dev)
- Push: Web Push (VAPID)
- Scheduler: APScheduler (in-process, hourly)
- Deploy: Railway + gunicorn --workers 1 --threads 4

## بنية المجلدات

husayniyyah_market/
├── app.py                 Flask app + extensions + context processors
├── database.py            SQLAlchemy instance
├── scheduler.py           APScheduler (subscription tasks)
├── models/                SQLAlchemy models (17 tables)
├── shared/                cross-cutting utilities
│   ├── decorators.py      @login_required, @role_required, @api_login_required
│   ├── security.py        rate limiting, Fernet encryption, IP resolution
│   ├── validators.py      email, phone, password, public_id
│   ├── utils.py           file upload, settings, redirects, time helpers
│   ├── repositories/      DB access layer (no business logic)
│   └── services/          business logic layer (no HTTP)
├── auth/                  register (3-step), login, password reset, account
├── customer/              market, stores, offers, cart, account, services
├── store_owner/           dashboard, products, orders, subscription
├── admin/                 users, stores, orders, subscriptions, finance
├── blueprints/
│   ├── api/               JWT API (auth, users, stores, products, orders, admin)
│   ├── delivery.py        delivery_bp (session) + delivery_api_bp (JWT)
│   ├── social.py          comments + reactions
│   └── reels.py           short video feed
├── notifications/         user notifications + push subscriptions
├── templates/             Jinja2 templates (RTL, Arabic-first)
├── static/                CSS, JS, vendor libraries
├── migrations/            Alembic versions (10 migrations)
├── tests/                 pytest suite (412 tests)
└── scripts/
    ├── init_db.py         bootstrap DB + admin
    ├── start_public.sh    start via cloudflared tunnel (dev)
    ├── benchmark.py       perf measurement (SQL query count + time)
    └── backup.sh          Postgres backup via Railway CLI

## الطبقات المعمارية

3-tier غير صارم:

1. Blueprint layer (HTTP) — request/response/flash/redirect.
2. Service layer (shared/services/) — business logic. لا يعرف HTTP.
3. Repository layer (shared/repositories/) — استعلامات DB. لا منطق.
4. Model layer (models/) — تعريفات الجداول + properties بسيطة.

قاعدة: mutations على الكيانات الحرجة (Order, Subscription, Cart) تُمرر عبر Services.

## خريطة Blueprints

- auth: /register, /login, /account (عام, CSRF نشط)
- market: /market, /, /search_suggestions (customer, CSRF نشط)
- stores: /stores, /store/<id>/public, /product/<id> (عام, CSRF نشط)
- offers: /offers (عام, CSRF نشط)
- services: /services, /support, /contact (عام + login, CSRF نشط)
- cart: /cart, /api/cart/sync (customer, CSRF نشط عدا sync)
- account: /favorites, /favorite/toggle, /product/<id>/review (customer, CSRF نشط)
- store: /store/<id>/*, /my_stores, /store/stats (owner, CSRF نشط)
- delivery: /delivery/* (delivery, CSRF نشط)
- delivery_api: /api/delivery/* (delivery JWT, CSRF معفى)
- admin: /admin/* (admin, CSRF نشط)
- api: /api/auth, /api/me, /api/stores, /api/orders, /api/admin (JWT, CSRF معفى)
- social: /api/products/<id>/comments, /api/comments/<id> (login, CSRF نشط)
- reels: /reels, /api/reels/* (عام/جزئي, CSRF نشط)
- notifications: /notifications, /api/notifications/* (login, CSRF نشط)

## دورة الطلب

new -> confirmed -> preparing -> ready -> delivering -> delivered
كل حالة يمكن أن تنتقل إلى cancelled (ما عدا delivered).

- OrderService.ALLOWED_TRANSITIONS تحكم الانتقالات.
- صاحب المتجر: confirmed, preparing, ready, cancelled.
- المندوب: delivering (بعد pickup_code), delivered (بعد delivery_code).
- الإدارة: كل الحالات.
- الزبون: cancelled (من new/confirmed/preparing فقط).

## المصادقة

Web sessions:
- لا نستخدم Flask-Login. مصادقة يدوية:
  - session['user_id'] + session['role'].
  - g.user يُملأ في before_request.
  - @login_required, @role_required من shared/decorators.py.
- CSRF عبر Flask-WTF على كل النماذج (عدا JWT API).
- Cookie: HttpOnly + SameSite=Lax + Secure في الإنتاج.

JWT API:
- /api/* (عدا updates) يستخدم @token_required (Bearer).
- HS256، صلاحية 1 يوم. لا refresh tokens حاليًا.

Rate limiting (4 طبقات):
1. Global (Flask-Limiter): 1000/day + 100/hour لكل IP.
2. DB-based auth: 5 محاولات/IP/5min + 15/حساب/15min على login/register.
3. In-memory subscription: 10 محاولات/IP/15min على verify_manual_confirmation.
4. In-memory uploads: 20/ساعة/IP على مسارات الرفع.

## Scheduler

scheduler.py مهمة كل ساعة (UTC) عبر APScheduler:
- check_expiring_subscriptions(days=3) — تنبيه قبل الانتهاء.
- expire_subscriptions() — احترام grace_days + auto_renew.

في الإنتاج: يُستدعى على مستوى الوحدة في app.py (داخل try/except).
محليًا: معطّل بـ SCHEDULER_ENABLED=0.
حماية التزامن: fcntl.flock + gunicorn --workers 1.

## الإشعارات

NotificationService — 3 قنوات:
1. DB — كل إشعار في جدول notifications.
2. Push — thread معزول يرسل Web Push (VAPID).
3. Polling — JS يستدعي /api/updates كل 30 ثانية للعدّاد.

## رفع الملفات

- Cloudinary إن مُهيأً. وإلا محليًا في static/uploads/.
- Magic bytes check على كل رفع (JPEG/PNG/GIF/WebP/MP4/AVI).
- Path traversal guard في delete_local_file.
- Image.MAX_IMAGE_PIXELS = 50M.
- Rate limit 20/ساعة/IP.

## النشر

- DB: Postgres (addon -> DATABASE_URL تلقائيًا).
- Procfile: web: flask db upgrade && flask create-admin && gunicorn app:app --workers 1 --threads 4 --timeout 120.
- إلزامي: FLASK_ENV=production, SECRET_KEY, JWT_SECRET_KEY, ADMIN_*.
- اختياري: CLOUDINARY_*, PUSH_ENABLED=1, VAPID_SUBJECT, SCHEDULER_ENABLED=1, TRUST_PROXY_HEADERS=1.

## قيود معروفة

1. app.py كبير (499 سطرًا) — يجمع extensions + context processors + error handlers. مرشح للتفكيك.
2. /my_stores مع 100+ متجر — يجلب كل المنتجات لعرض 8.
3. shared/utils.py (~450 سطرًا) — مرشح للتفكيك.
4. user_activity cache في الذاكرة — يعمل مع --workers 1 فقط.
5. لا refresh tokens للـ JWT — المستخدم يعيد الدخول بعد 24 ساعة.
