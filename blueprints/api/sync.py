# تم إفراغ هذا الملف في مراجعة v1.
#
# السبب: كان يحتوي على مسارات /api/cart/sync و /api/favorites/sync و /api/profile/sync
# بنسخة JWT (token_required)، لكن نفس المسارات موجودة بنسخة الجلسة (session) في:
#   - customer/cart.py        → /api/cart/sync
#   - customer/account.py     → /api/favorites/sync
#   - auth/account.py         → /api/profile/sync
#
# Flask يسجّل api_bp قبل customer/* في app.py، فكانت النسخة JWT هي التي تُلتقط،
# بينما localStore.js يرسل cookies فقط دون Bearer token → 401 صامت في كل مزامنة.
#
# الحل: الاعتماد على النسخ المعتمدة على الجلسة (مناسبة لمنصة ويب/PWA).
# عند الحاجة لتطبيق جوال مستقبلي، نضيف مسارات JWT بمسارات مختلفة (مثل /api/v1/...).
