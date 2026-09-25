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

RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt \
 && python -c "import psycopg2; print('BUILD-CHECK-1:', psycopg2.__version__)"

# طبقة تشخيصية: تسجّل حالة المكتبات داخل الصورة
RUN pip list > /app/.pip-list-at-build.txt \
 && ls -la /usr/local/lib/python3.11/site-packages/ > /app/.site-packages-at-build.txt \
 && python -c "import psycopg2; print(psycopg2.__file__)" > /app/.psycopg2-path-at-build.txt

COPY . .

RUN chmod +x /app/start.sh

EXPOSE 8000

CMD ["/app/start.sh"]
