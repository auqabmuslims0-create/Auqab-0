from functools import wraps
from flask import session, redirect, url_for, flash, abort, jsonify
from database import db
from models import User

def login_required(f):
    """يتطلب تسجيل الدخول (لصفحات الويب)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('يجب تسجيل الدخول أولاً', 'error')
            return redirect(url_for('auth.login'))
        user = db.session.get(User, session['user_id'])
        if not user or not user.is_active:
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
            if 'user_id' not in session:
                flash('يجب تسجيل الدخول أولاً', 'error')
                return redirect(url_for('auth.login'))
            user = db.session.get(User, session['user_id'])
            if not user or not user.is_active or user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return decorator

def api_login_required(f):
    """يتطلب تسجيل الدخول (لـ API التي تستخدم الجلسة)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'status': 'error', 'message': 'يجب تسجيل الدخول'}), 401
        user = db.session.get(User, session['user_id'])
        if not user or not user.is_active:
            return jsonify({'status': 'error', 'message': 'جلسة غير صالحة أو حساب موقوف'}), 401
        return f(*args, **kwargs)
    return wrapper
