#!/usr/bin/env bash
# backup.sh — نسخ احتياطي لـ Postgres الإنتاج (Railway)
#
# المتطلبات:
#   railway CLI: npm i -g @railway/cli && railway login
#   المشروع مربوط: cd ~/husayniyyah_market && railway link
#
# الاستخدام:
#   bash scripts/backup.sh
#   bash scripts/backup.sh --keep 14
#
# النسخ في ~/backups/husayniyyah/YYYY-MM-DD_HHMMSS.sql.gz

set -euo pipefail

BACKUP_ROOT="${HOME}/backups/husayniyyah"
KEEP=7

while [ $# -gt 0 ]; do
    case "$1" in
        --keep) KEEP="$2"; shift 2 ;;
        --help|-h)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

mkdir -p "$BACKUP_ROOT"

TIMESTAMP=$(date +"%Y-%m-%d_%H%M%S")
OUT_FILE="${BACKUP_ROOT}/${TIMESTAMP}.sql.gz"

echo "[backup] Project: $(pwd)"
echo "[backup] Output : ${OUT_FILE}"

if ! command -v railway >/dev/null 2>&1; then
    echo "[backup] ERROR: railway CLI غير مثبتة."
    echo "[backup] install: npm i -g @railway/cli"
    exit 1
fi

echo "[backup] Running pg_dump via Railway..."
if railway run bash -c 'pg_dump "$DATABASE_URL"' | gzip > "$OUT_FILE"; then
    SIZE=$(du -h "$OUT_FILE" | cut -f1)
    echo "[backup] OK — ${OUT_FILE} (${SIZE})"
else
    echo "[backup] ERROR: pg_dump فشل"
    rm -f "$OUT_FILE"
    exit 1
fi

echo "[backup] Rotating: keep last ${KEEP} backups"
cd "$BACKUP_ROOT"
ls -1t *.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
    echo "[backup]   removing ${old}"
    rm -f "$old"
done

echo "[backup] Current backups:"
ls -lh "$BACKUP_ROOT"/*.sql.gz 2>/dev/null || echo "  (none)"

echo "[backup] Done."
