from flask import session, redirect, url_for, abort, flash, g
from database import db
from models import Store


def check_store_access(store_id):
    """
    التحقق من أن المستخدم الحالي هو صاحب المتجر وأنه نشط.

    يرجع (user, store) أو (None, redirect_response) في حال الخطأ.

    ملاحظة أمنية: عند عدم الملكية نُرجع 404 (بدل 403) لتفادي كشف وجود المتجر
    لمستخدم غير مصرح (User Enumeration).
    """
    user = g.user
    if not user:
        flash('يجب تسجيل الدخول أولاً', 'error')
        return None, redirect(url_for('auth.login'))

    if not user.is_active:
        session.clear()
        flash('حسابك محظور، يرجى التواصل مع الإدارة', 'error')
        return None, redirect(url_for('auth.login'))

    store = db.session.get(Store, store_id)
    if not store:
        abort(404)

    if store.owner_id != user.id:
        abort(404)

    return user, store
