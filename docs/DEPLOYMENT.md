# دليل النشر على Railway

## المتطلبات

- حساب railway.app
- GitHub repo متصل
- (اختياري) Cloudinary + VAPID

---

## 1) مشروع Railway

- New Project -> Deploy from GitHub repo
- اختر Auqab-0

## 2) PostgreSQL

- + New -> Database -> Add PostgreSQL
- DATABASE_URL يضاف تلقائياً

## 3) متغيرات البيئة

Variables -> Raw Editor:

    FLASK_ENV=production
    FLASK_DEBUG=0
    SECRET_KEY=<64-char-random>
    JWT_SECRET_KEY=<64-char-random>

    ADMIN_USERNAME=admin
    ADMIN_EMAIL=you@example.com
    ADMIN_PHONE=+963xxxxxxxxx
    ADMIN_PASSWORD=<strong>

    CLOUDINARY_CLOUD_NAME=<your-cloud>
    CLOUDINARY_API_KEY=<your-key>
    CLOUDINARY_API_SECRET=<your-secret>

    SCHEDULER_ENABLED=1
    TRUST_PROXY_HEADERS=1

## 4) توليد SECRET_KEY

    python3 -c "import secrets; print(secrets.token_hex(32))"

## 5) النشر

Railway ينفذ Procfile تلقائياً:
- flask db upgrade
- flask create-admin
- gunicorn

---

## Troubleshooting

### SECRET_KEY must be set
- تأكد FLASK_ENV=production و SECRET_KEY موجود

### flask db upgrade يفشل
- تحقق DATABASE_URL
- railway run flask db upgrade

### 502/504
- زد --timeout إلى 180 في Procfile

---

## Backup

    railway run pg_dump $DATABASE_URL > backup.sql

استرجاع:

    railway run psql $DATABASE_URL < backup.sql
