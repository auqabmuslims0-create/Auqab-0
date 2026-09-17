# سوق الحسينية — Husayniyyah Market

منصة سوق إلكتروني متكاملة (ويب + PWA) مبنية بـ Flask.
تدعم متاجر متعددة، مندوبي توصيل، اشتراكات، إشعارات فورية (Web Push)، وريلز.

---

## المزايا

- متاجر متعددة مع اشتراكات شهرية
- سلة مشتريات ذكية (متزامنة)
- 4 أدوار: أدمن، صاحب متجر، مندوب، زبون
- توصيل بـ GPS (Leaflet + OSRM)
- إشعارات فورية (Web Push)
- ريلز
- PWA (يعمل أوفلاين + قابل للتثبيت)
- تقييمات وتعليقات
- نظام مالي
- Chat مع الإدارة

---

## التقنيات

- Backend: Flask 3, SQLAlchemy 3, Alembic
- Database: SQLite (dev) / PostgreSQL (prod)
- Frontend: Bootstrap 5 RTL
- PWA + Service Worker + Web Push
- Media: Cloudinary + ffmpeg
- Deployment: Railway
- Scheduler: APScheduler

---

## المتطلبات

- Python 3.11+
- pip + venv
- (اختياري) ffmpeg
- (اختياري) tzdata

---

## التنصيب المحلي

1) استنساخ:

    git clone https://github.com/auqabmuslims0-create/husayniyyah_market.git
    cd husayniyyah_market

2) بيئة Python:

    python3 -m venv venv
    source venv/bin/activate

3) تثبيت الحزم:

    pip install -r requirements.txt

4) متغيرات البيئة:

    cp .env.example .env

5) قاعدة البيانات:

    flask db upgrade
    flask create-admin

6) تشغيل:

    FLASK_DEBUG=1 flask run --host=0.0.0.0 --port=8000

افتح http://localhost:8000

---

## النشر

انظر docs/DEPLOYMENT.md

---

## بنية المشروع

    app.py                     نقطة الدخول
    Procfile                   Railway start
    runtime.txt                Python version
    requirements.txt
    .env.example
    admin/                     Blueprint: أدمن
    auth/                      Blueprint: مصادقة
    blueprints/                متنوعة (api, delivery, reels, social)
    customer/                  واجهة الزبون
    notifications/             إشعارات
    store_owner/               صاحب المتجر
    models/                    SQLAlchemy Models
    shared/                    كود مشترك
    migrations/                Alembic
    scheduler.py               APScheduler
    templates/                 Jinja2
    static/                    CSS, JS, Vendors
    docs/DEPLOYMENT.md

---

## الأدوار

- admin: كل الصفحات + الإدارة + المالية
- owner: متاجره + منتجاته + طلباته
- delivery: المندوب + الطلبات المتاحة
- customer: السوق + السلة + المفضلة

---

## الأمان

- Session auth + cookies HttpOnly
- CSRF protection
- Rate limiting (5 login attempts/5min)
- CSP headers (Talisman)
- Werkzeug scrypt
- Store ownership checks

---

جميع الحقوق محفوظة (c) سوق الحسينية 2024.
