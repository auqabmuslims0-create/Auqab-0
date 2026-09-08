from flask import session, redirect, url_for, abort, flash
from database import db
from models import User, Store

def check_store_access(store_id):
    """التحقق من أن المستخدم الحالي هو صاحب المتجر وأنه نشط.
    يرجع (user, store) أو (None, redirect_response) في حال الخطأ.
    """
    if 'user_id' not in session:
        flash('يجب تسجيل الدخول أولاً', 'error')
        return None, redirect(url_for('auth.login'))

    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        flash('الجلسة غير صالحة، يرجى تسجيل الدخول مرة أخرى', 'error')
        return None, redirect(url_for('auth.login'))

    if not user.is_active:
        session.clear()
        flash('حسابك محظور، يرجى التواصل مع الإدارة', 'error')
        return None, redirect(url_for('auth.login'))

    store = db.session.get(Store, store_id)
    if not store:
        abort(404)

    if store.owner_id != user.id:
        abort(403)

    return user, store
