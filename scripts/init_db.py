import os
import sys

# التأكد من استيراد التطبيق بشكل صحيح
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import app, ensure_admin
from database import db
import models  # noqa: F401 لضمان تسجيل النماذج

with app.app_context():
    print("تطبيق ترحيلات قاعدة البيانات (flask db upgrade)...")
    # استخدام flask_migrate بدلاً من db.create_all
    from flask_migrate import upgrade
    upgrade()

    print("تم تطبيق الترحيلات بنجاح.")
    print("إنشاء المدير الافتراضي...")
    ensure_admin()
    print("اكتملت التهيئة.")
