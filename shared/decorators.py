from functools import wraps
from flask import session, redirect, url_for, flash, abort, jsonify, g
from database import db
from models import User


def _get_current_user():
    """
    يرجع المستخدم الحالي من g إن وُجد، وإلا يستعلم مرة واحدة ويحفظه.
    هذا يمنع 3 استعلامات User مكررة لكل طلب (g.user + login_required + role_required).
    """
    if hasattr(g, 'user'):
        return g.user
    user_id = session.get('user_id')
    if not user_id:
        g.user = None
        return None
    user = db.session.get(User, user_id)
    g.user = user
    return user


def login_required(f):
    """يتطلب تسجيل الدخول (لصفحات الويب)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = _get_current_user()
        if not user:
            flash('يجب تسجيل الدخول أولاً', 'error')
            return redirect(url_for('auth.login'))
        if not user.is_active:
            session.clear()
            flash('الجلسة غير صالحة، يرجى تسجيل الدخول', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return wrapper


def role_required(*roles):
    """يتطلب دورًا محددًا (مثل admin, owner, delivery)."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = _get_current_user()
            if not user:
                flash('يجب تسجيل الدخول أولاً', 'error')
                return redirect(url_for('auth.login'))
            if not user.is_active or user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return decorator


def api_login_required(f):
    """يتطلب تسجيل الدخول (لـ API التي تستخدم الجلسة)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = _get_current_user()
        if not user:
            return jsonify({'status': 'error', 'message': 'يجب تسجيل الدخول'}), 401
        if not user.is_active:
            return jsonify({'status': 'error', 'message': 'جلسة غير صالحة أو حساب موقوف'}), 401
        return f(*args, **kwargs)
    return wrapper
