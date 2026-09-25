#!/bin/sh
echo "========== RUNTIME DIAGNOSTICS =========="
echo "1. Which python is used?"
which python && python --version

echo ""
echo "2. Which flask is used?"
which flask && head -1 $(which flask)

echo ""
echo "3. Is psycopg2 in pip list?"
pip list 2>/dev/null | grep -i psycopg || echo "   NOT FOUND in pip list"

echo ""
echo "4. Is psycopg2 in site-packages?"
ls /usr/local/lib/python3.11/site-packages/ | grep -i psycopg || echo "   NOT FOUND in site-packages"

echo ""
echo "5. Can python import psycopg2?"
python -c "import psycopg2; print('   OK:', psycopg2.__version__, '->', psycopg2.__file__)" 2>&1 || echo "   IMPORT FAILED"

echo ""
echo "6. sys.path first 5 entries:"
python -c "import sys; print('\n'.join('   ' + p for p in sys.path[:5]))"

echo ""
echo "========== STARTING APP =========="
flask db upgrade
flask create-admin
exec gunicorn app:app --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:${PORT:-8000}
