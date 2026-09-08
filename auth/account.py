from flask import render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from database import db
from models import User
from shared.repositories.user_repository import UserRepository
from shared.validators import is_valid_email, is_valid_phone_syrian, is_strong_password
from shared.utils import save_image, get_upload_path
from shared.services.user_service import UserService
from shared.decorators import login_required
from . import auth_bp
import os

@auth_bp.route('/account')
@login_required
def account():
    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))
    return render_template('customer/account.html', user=user)

@auth_bp.route('/account/theme', methods=['POST'])
@login_required
def update_theme_preference():
    user = db.session.get(User, session['user_id'])
    if not user:
        return jsonify({'status': 'error', 'message': 'غير مسموح'}), 401

    data = request.get_json(silent=True) or {}
    dark_mode = data.get('dark_mode', None)

    if dark_mode is None:
        return jsonify({'status': 'error', 'message': 'قيمة غير صالحة'}), 400

    if isinstance(dark_mode, str):
        dark_mode = dark_mode.lower() == 'true'
    if not isinstance(dark_mode, bool):
        return jsonify({'status': 'error', 'message': 'قيمة غير صالحة'}), 400

    user.dark_mode = dark_mode
    db.session.commit()
    session['dark_mode'] = dark_mode

    return jsonify({'status': 'success', 'dark_mode': user.dark_mode})

@auth_bp.route('/api/profile/sync', methods=['POST'])
@login_required
def profile_sync():
    user = db.session.get(User, session['user_id'])
    if not user:
        return jsonify({'status': 'error', 'message': 'غير مسموح'}), 401

    data = request.get_json(silent=True) or {}
    username = data.get('username', user.username).strip()
    email = data.get('email', user.email).strip()
    phone = data.get('phone', '').strip()
    bio = data.get('bio', user.bio or '').strip()

    if not username or not email:
        return jsonify({'status': 'error', 'message': 'الاسم والبريد مطلوبان'}), 400
    if not is_valid_email(email):
        return jsonify({'status': 'error', 'message': 'البريد غير صالح'}), 400

    existing_username = User.query.filter(User.username == username, User.id != user.id).first()
    if existing_username:
        return jsonify({'status': 'error', 'message': 'اسم المستخدم موجود'}), 400
    existing_email = User.query.filter(User.email == email, User.id != user.id).first()
    if existing_email:
        return jsonify({'status': 'error', 'message': 'البريد مستخدم'}), 400

    if phone:
        if not is_valid_phone_syrian(phone):
            return jsonify({'status': 'error', 'message': 'رقم الهاتف غير صالح'}), 400
        user.phone = '+963' + phone
    else:
        user.phone = None

    user.username = username
    user.email = email
    user.bio = bio

    try:
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'تم تحديث الملف الشخصي'})
    except Exception:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'حدث خطأ أثناء الحفظ'}), 500

@auth_bp.route('/account/unlock', methods=['POST'])
@login_required
def account_unlock():
    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    password = request.form.get('password', '')
    if check_password_hash(user.password_hash, password):
        session['account_unlocked'] = True
        flash('تم فتح الأقسام المحمية', 'success')
    else:
        flash('كلمة المرور غير صحيحة', 'error')
    return redirect(url_for('auth.account'))

@auth_bp.route('/account/lock')
@login_required
def account_lock():
    session.pop('account_unlocked', None)
    flash('تم قفل الأقسام. ستحتاج كلمة المرور لفتحها مرة أخرى.', 'info')
    return redirect(url_for('auth.account'))

@auth_bp.route('/account/update', methods=['POST'])
@login_required
def account_update():
    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    bio = request.form.get('bio', '').strip()

    if not username or not email:
        flash('اسم المستخدم والبريد الإلكتروني مطلوبان', 'error')
        return redirect(url_for('auth.account'))

    if not is_valid_email(email):
        flash('البريد الإلكتروني غير صالح', 'error')
        return redirect(url_for('auth.account'))

    existing_username = User.query.filter(User.username == username, User.id != user.id).first()
    if existing_username:
        flash('اسم المستخدم موجود مسبقاً', 'error')
        return redirect(url_for('auth.account'))

    existing_email = User.query.filter(User.email == email, User.id != user.id).first()
    if existing_email:
        flash('البريد الإلكتروني مستخدم بالفعل', 'error')
        return redirect(url_for('auth.account'))

    user.username = username
    user.email = email
    if phone:
        if not is_valid_phone_syrian(phone):
            flash('رقم الهاتف يجب أن يبدأ بـ 9 ويتكون من 9 أرقام', 'error')
            return redirect(url_for('auth.account'))
        user.phone = '+963' + phone
    else:
        user.phone = None

    user.bio = bio

    avatar_file = request.files.get('avatar')
    if avatar_file and avatar_file.filename != '':
        try:
            old_avatar_url = user.avatar
            avatar_url = save_image(avatar_file, old_url=old_avatar_url)
        except Exception as e:
            flash(f'استثناء أثناء الرفع: {str(e)}', 'error')
            return redirect(url_for('auth.account'))
        if avatar_url:
            flash('تم رفع الصورة بنجاح', 'success')
            user.avatar = avatar_url
        else:
            flash('فشل رفع الصورة - save_image أرجعت None', 'error')
            return redirect(url_for('auth.account'))

    db.session.commit()
    flash('تم تحديث بيانات الحساب بنجاح', 'success')
    return redirect(url_for('auth.account'))

@auth_bp.route('/account/change_password', methods=['POST'])
@login_required
def account_change_password():
    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not current_password or not new_password or not confirm_password:
        flash('جميع الحقول مطلوبة', 'error')
        return redirect(url_for('auth.account'))

    if not check_password_hash(user.password_hash, current_password):
        flash('كلمة المرور الحالية غير صحيحة', 'error')
        return redirect(url_for('auth.account'))

    if new_password != confirm_password:
        flash('كلمتا المرور غير متطابقتين', 'error')
        return redirect(url_for('auth.account'))

    strong, msg = is_strong_password(new_password)
    if not strong:
        flash(msg, 'error')
        return redirect(url_for('auth.account'))

    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    flash('تم تغيير كلمة المرور بنجاح', 'success')
    return redirect(url_for('auth.account'))

@auth_bp.route('/account/delete', methods=['POST'])
@login_required
def account_delete():
    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    success, msg = UserService.delete_user_fully(user.id)
    if success:
        session.clear()
        flash(msg, 'success')
        return redirect(url_for('auth.register'))
    else:
        flash(msg, 'error')
        return redirect(url_for('auth.account'))
