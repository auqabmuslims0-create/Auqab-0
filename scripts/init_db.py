import os
import sys

# التأكد من استيراد التطبيق بشكل صحيح
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import app, ensure_admin
from database import db
import models  # noqa: F401 لضمان تسجيل النماذج

with app.app_context():
    print("فحص حالة قاعدة البيانات والترحيلات...")

    from flask_migrate import upgrade, current, heads

    try:
        current_revision = current()
    except Exception:
        current_revision = None

    try:
        head_revision = heads()
    except Exception:
        head_revision = None

    if head_revision and current_revision != head_revision[0]:
        print(f"الترحيل الحالي: {current_revision or 'لا يوجد'}")
        print(f"أحدث ترحيل: {head_revision[0]}")
        print("تطبيق ترحيلات قاعدة البيانات (flask db upgrade)...")
        upgrade()
        print("تم تطبيق الترحيلات بنجاح.")
    else:
        print("قاعدة البيانات محدثة، لا حاجة لتطبيق ترحيلات.")

    print("إنشاء المدير الافتراضي...")
    ensure_admin()
    print("اكتملت التهيئة.")
