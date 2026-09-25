FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# تثبيت صريح + التحقق الفوري من psycopg2
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && python -c "import psycopg2; print('BUILD-CHECK: psycopg2 v' + psycopg2.__version__ + ' OK')"

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "flask db upgrade && flask create-admin && gunicorn app:app --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:${PORT:-8000}"]
