#!/bin/sh
echo "========== RUNTIME DIAGNOSTICS =========="
echo "1. Python binaries comparison:"
echo "   /usr/local/bin/python   → $(readlink -f /usr/local/bin/python)"
echo "   /usr/local/bin/python3.11 → $(readlink -f /usr/local/bin/python3.11)"
ls -la /usr/local/bin/python* 2>&1 | head -5

echo ""
echo "2. Flask shebang:"
head -1 /usr/local/bin/flask

echo ""
echo "3. Import test with python:"
python -c "import psycopg2; print('   ✅ python:', psycopg2.__version__)" 2>&1

echo ""
echo "4. Import test with python3.11:"
/usr/local/bin/python3.11 -c "import psycopg2; print('   ✅ python3.11:', psycopg2.__version__)" 2>&1 || echo "   ❌ python3.11 FAILED"

echo ""
echo "========== STARTING APP (using python -m flask) =========="
python -m flask db upgrade
python -m flask create-admin
exec python -m gunicorn app:app --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:${PORT:-8000}
