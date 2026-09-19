# Contributing — سوق الحسينية

## إعداد بيئة التطوير

### Termux (Android)

pkg install python git
git clone https://github.com/auqabmuslims0-create/Auqab-0.git
cd Auqab-0
pip install -r requirements.txt
pip install -r requirements-dev.txt
cp .env.example .env
python scripts/init_db.py
python app.py    # http://0.0.0.0:8000

### Linux / macOS

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
python scripts/init_db.py
python app.py

## الاختبارات

pytest                                              كل الاختبارات (412)
pytest tests/test_auth.py -v                        ملف واحد
pytest tests/test_auth.py::test_login_success -v    اختبار واحد
pytest --cov=. --cov-report=term-missing            مع coverage

### قواعد كتابة الاختبارات

- صفر تسريب: clean_db fixture تُعيد بناء DB قبل كل اختبار.
- صفر تلويث: استخدم temp_static_folder (monkeypatch) للاختبارات التي ترفع ملفات.
- صفر شبكة: VAPID/Cloudinary معطّلة في conftest.py.
- CSRF: معطّل افتراضيًا. للتفعيل: _csrf_enabled(app) context manager.

## قواعد الكود

### عام

- 4 مسافات indent.
- أسطر أقل من 120 حرفًا.
- UTF-8.

### Flask

- Blueprint لكل دور.
- @role_required('owner') قبل أي منطق في مسارات owner.
- Session blueprints تحتاج CSRF — أي blueprint غير معفى يجب أن يستقبل
  X-CSRF-Token أو csrf_token في form.

### Models

- لا db.create_all() في الإنتاج.
- CheckConstraint على أي enum بصيغة String.
- Indexes على الأعمدة المتكررة في filter/order.

### Services

- منطق الأعمال المعقد في shared/services/.
- يرفع ValueError / PermissionError بوضوح.
- لا يعرف HTTP.
- يعيد (success, message, data) عند الحاجة.

### Repositories

- استعلامات DB فقط. لا منطق.

## نمط الـ Commit

الصيغة:
  type(scope): subject

  Body: ماذا ولماذا (ليس كيف).

  Tests: X total (was Y).

الأنواع: feat, fix, security, perf, refactor, test, docs, chore.

أمثلة:
- fix(scheduler): run scheduler at module level (works under gunicorn)
- security(auth): harden session, rate limiting, and reset flow
- perf+security: fix N+1 on /my_stores, cap /cart orders, POST-only logout

## قائمة مراجعة قبل الـ Commit

- pytest -v — كل الاختبارات تمر.
- python -c "import app; print('OK')" — لا أخطاء استيراد.
- لا print() تركتها.
- لا ملفات .bak أو .pyc أو .db أو .env في git status.
- الـ commit message يصف السبب.
- إن كان تغيير schema: flask db migrate + مراجعة الـ migration.

## قائمة مراجعة قبل النشر

- git push نجح.
- Railway Deploy Logs — لا traceback.
- "تم بدء المجدول الدوري" ظهر في logs.
- اختبار يدوي: /login + /market + /admin.
- لا "SECRET_KEY must be set".

## قواعد الأمان

لا تفعل:
- لا |safe في Jinja على بيانات user-controlled.
- لا eval() / exec() على مدخلات المستخدم.
- لا subprocess.run(..., shell=True).
- لا logging لبيانات حساسة.
- لا try: except: pass صامت.
- لا تخزين password_hash في كوكي بدون تشفير.

افعل:
- @role_required على كل مسار إداري.
- تحقق من ملكية الموارد (order.customer_id == user.id).
- safe_redirect_target على أي next URL.
- _validate_image_magic قبل قبول أي ملف.
- ارفع استثناء واضح بدل None ضمنيًا.

## أسئلة شائعة

كيف أختبر push محليًا؟
صعب بدون VAPID حقيقي. الاختبارات الحالية تتحقق من الحفظ في DB فقط.
للإرسال الفعلي: PUSH_ENABLED=1 + VAPID_SUBJECT + subscription من متصفح حقيقي.

كيف أضيف نموذجًا؟
1. models/new_model.py
2. أضفه إلى models/__init__.py
3. flask db migrate -m "add new_model"
4. راجع migrations/versions/<hash>_*.py
5. flask db upgrade
6. أضف اختبارات

كيف أسرّع الاختبارات؟
scrypt بطيء على Termux. جرّب: pytest -x (توقف عند أول فشل)،
أو اختبار ملف واحد.
