from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash
from database import db
from models import User, PasswordReset
from shared.repositories.user_repository import UserRepository
import secrets
import hashlib
from datetime import timedelta
from shared.validators import is_strong_password
from shared.security import record_reset_attempt, get_reset_attempts_by_email, get_reset_attempts_by_ip
from shared.time_utils import current_time
from . import auth_bp

@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip:
            ip = ip.split(',')[0].strip()

        if get_reset_attempts_by_email(email) >= 3:
            flash('تم تجاوز عدد محاولات استعادة كلمة المرور، حاول بعد 15 دقيقة', 'error')
            return redirect(url_for('auth.forgot_password'))

        if get_reset_attempts_by_ip(ip) >= 5:
            flash('تم تجاوز عدد محاولات استعادة كلمة المرور من هذا الجهاز، حاول بعد 15 دقيقة', 'error')
            return redirect(url_for('auth.forgot_password'))

        user = UserRepository.get_by_email(email)
        if not user:
            record_reset_attempt(email, ip)
            flash('إذا كان البريد مسجلاً، فسيتم إرسال تعليمات استعادة كلمة المرور', 'info')
            return redirect(url_for('auth.login'))

        record_reset_attempt(email, ip)
        session['reset_email'] = email
        return redirect(url_for('auth.confirm_identity'))

    return render_template('auth/forgot_password.html')

@auth_bp.route('/confirm_identity', methods=['GET', 'POST'])
def confirm_identity():
    email = session.get('reset_email')
    if not email:
        flash('يرجى إدخال بريدك أولاً', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        phone = request.form.get('phone', '').strip()
        public_id = request.form.get('public_id', '').strip()
        role = request.form.get('role', '').strip()

        if not username or not phone or not public_id or not role:
            flash('جميع الحقول مطلوبة', 'error')
            return redirect(url_for('auth.confirm_identity'))

        user = UserRepository.get_by_email(email)
        expected_phone = '+963' + phone if phone else ''
        if not user or user.username != username or user.phone != expected_phone or user.public_id != public_id or user.role != role:
            flash('بيانات الهوية غير صحيحة', 'error')
            return redirect(url_for('auth.confirm_identity'))

        PasswordReset.query.filter_by(user_id=user.id).delete()
        token = secrets.token_hex(20)
        hashed_token = hashlib.sha256(token.encode()).hexdigest()
        reset = PasswordReset(
            user_id=user.id,
            token=hashed_token,
            expires_at=current_time() + timedelta(hours=1)
        )
        db.session.add(reset)
        db.session.commit()

        session.pop('reset_email', None)
        session['reset_user_id'] = user.id
        return redirect(url_for('auth.reset_password', token=token))

    return render_template('auth/confirm_identity.html')

@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
@auth_bp.route('/reset_password', methods=['GET', 'POST'])
def reset_password(token=None):
    reset = None
    if token:
        hashed_token = hashlib.sha256(token.encode()).hexdigest()
        reset = PasswordReset.query.filter_by(token=hashed_token).first()
        if not reset or reset.expires_at < current_time():
            flash('الرابط غير صالح أو منتهي', 'error')
            return redirect(url_for('auth.forgot_password'))
    else:
        user_id = session.get('reset_user_id')
        if not user_id:
            flash('جلسة استعادة غير صالحة', 'error')
            return redirect(url_for('auth.forgot_password'))
        reset = PasswordReset.query.filter_by(user_id=user_id).order_by(PasswordReset.expires_at.desc()).first()
        if not reset or reset.expires_at < current_time():
            flash('انتهت صلاحية الجلسة، يرجى إعادة العملية', 'error')
            return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if new_password != confirm_password:
            flash('كلمتا المرور غير متطابقتين', 'error')
            return redirect(url_for('auth.reset_password', token=token or ''))

        strong, msg = is_strong_password(new_password)
        if not strong:
            flash(msg, 'error')
            return redirect(url_for('auth.reset_password', token=token or ''))

        user = db.session.get(User, reset.user_id)
        if not user:
            flash('المستخدم غير موجود', 'error')
            return redirect(url_for('auth.forgot_password'))

        user.password_hash = generate_password_hash(new_password)
        db.session.delete(reset)
        db.session.commit()
        session.pop('reset_user_id', None)
        flash('تم تغيير كلمة المرور بنجاح', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token or '')
