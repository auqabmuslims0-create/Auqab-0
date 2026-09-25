# ============================================================
# Dockerfile — يتجاوز Nixpacks و mise تماماً
# يضمن تثبيت psycopg2-binary في المكان الصحيح
# ============================================================

FROM python:3.11-slim

# متغيرات بيئة محسّنة
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# حزم النظام المطلوبة (libpq لـ psycopg2، gcc كاحتياط للبناء)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# مجلد العمل
WORKDIR /app

# نسخ requirements أولاً (طبقة cache)
COPY requirements.txt .

# تثبيت كل الحزم بشكل صريح في python النظامي
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

# نسخ التطبيق كاملاً
COPY . .

# المنفذ الذي يستخدمه Railway
EXPOSE 8000

# أمر التشغيل (يطابق Procfile)
CMD ["sh", "-c", "flask db upgrade && flask create-admin && gunicorn app:app --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:${PORT:-8000}"]
