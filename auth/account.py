from flask import (
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    g,
    current_app,
)
from werkzeug.security import generate_password_hash, check_password_hash
from database import db
from models import User
from shared.validators import is_valid_email, is_valid_phone_syrian, is_strong_password
from shared.utils import save_image
from shared.services.user_service import UserService
from shared.decorators import login_required
from shared.security import (
    get_client_ip,
    get_login_attempts,
    record_login_attempt,
    clear_login_attempts,
)
from . import auth_bp


def _validate_profile_updates(user, username, email, phone, bio):
    """
    تحقق مشترك لتحديث الملف الشخصي (يُستخدم من النموذج و JSON API).

    يعيد: (success: bool, error_msg: str|None, normalized: dict|None)
      normalized = {
          'username': str,
          'email': str,
          'phone': str|None,   # '+963XXXXXXXXX' أو None
          'bio': str,
      }
    """
    if not username or not email:
        return False, 'اسم المستخدم والبريد الإلكتروني مطلوبان', None

    if not is_valid_email(email):
        return False, 'البريد الإلكتروني غير صالح', None

    existing_username = User.query.filter(
        User.username == username, User.id != user.id
    ).first()
    if existing_username:
        return False, 'اسم المستخدم موجود مسبقاً', None

    existing_email = User.query.filter(
        User.email == email, User.id != user.id
    ).first()
    if existing_email:
        return False, 'البريد الإلكتروني مستخدم بالفعل', None

    normalized_phone = None
    if phone:
        if not is_valid_phone_syrian(phone):
            return False, 'رقم الهاتف يجب أن يبدأ بـ 9 ويتكون من 9 أرقام', None
        normalized_phone = '+963' + phone

    return True, None, {
        'username': username,
        'email': email,
        'phone': normalized_phone,
        'bio': bio,
    }


@auth_bp.route('/account')
@login_required
def account():
    user = g.user
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))
    return render_template('customer/account.html', user=user)


@auth_bp.route('/account/theme', methods=['POST'])
@login_required
def update_theme_preference():
    user = g.user
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
    user = g.user
    if not user:
        return jsonify({'status': 'error', 'message': 'غير مسموح'}), 401

    data = request.get_json(silent=True) or {}
    username = data.get('username', user.username).strip()
    email = data.get('email', user.email).strip()
    phone = data.get('phone', '').strip()
    bio = data.get('bio', user.bio or '').strip()

    ok, err, normalized = _validate_profile_updates(user, username, email, phone, bio)
    if not ok:
        return jsonify({'status': 'error', 'message': err}), 400

    user.username = normalized['username']
    user.email = normalized['email']
    user.phone = normalized['phone']
    user.bio = normalized['bio']

    try:
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'تم تحديث الملف الشخصي'})
    except Exception:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'حدث خطأ أثناء الحفظ'}), 500


@auth_bp.route('/account/unlock', methods=['POST'])
@login_required
def account_unlock():
    user = g.user
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    ip = get_client_ip()
    if get_login_attempts(ip) >= 5:
        flash('تم تجاوز عدد المحاولات المسموح، حاول بعد 5 دقائق', 'error')
        return redirect(url_for('auth.account'))

    password = request.form.get('password', '')
    if check_password_hash(user.password_hash, password):
        session['account_unlocked'] = True
        clear_login_attempts(ip)
        flash('تم فتح الأقسام المحمية', 'success')
    else:
        record_login_attempt(ip)
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
    user = g.user
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    bio = request.form.get('bio', '').strip()

    ok, err, normalized = _validate_profile_updates(user, username, email, phone, bio)
    if not ok:
        flash(err, 'error')
        return redirect(url_for('auth.account'))

    user.username = normalized['username']
    user.email = normalized['email']
    user.phone = normalized['phone']
    user.bio = normalized['bio']

    avatar_file = request.files.get('avatar')
    if avatar_file and avatar_file.filename != '':
        try:
            old_avatar_url = user.avatar
            avatar_url = save_image(avatar_file, old_url=old_avatar_url)
        except Exception as e:
            current_app.logger.error(
                f'avatar upload failed for user_id={user.id}: {str(e)}'
            )
            flash('تعذر رفع الصورة، يرجى المحاولة مرة أخرى', 'error')
            return redirect(url_for('auth.account'))
        if avatar_url:
            flash('تم رفع الصورة بنجاح', 'success')
            user.avatar = avatar_url
        else:
            flash('تعذر رفع الصورة، يرجى المحاولة مرة أخرى', 'error')
            return redirect(url_for('auth.account'))

    db.session.commit()
    flash('تم تحديث بيانات الحساب بنجاح', 'success')
    return redirect(url_for('auth.account'))


@auth_bp.route('/account/change_password', methods=['POST'])
@login_required
def account_change_password():
    user = g.user
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    ip = get_client_ip()
    if get_login_attempts(ip) >= 5:
        flash('تم تجاوز عدد المحاولات المسموح، حاول بعد 5 دقائق', 'error')
        return redirect(url_for('auth.account'))

    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not current_password or not new_password or not confirm_password:
        flash('جميع الحقول مطلوبة', 'error')
        return redirect(url_for('auth.account'))

    if not check_password_hash(user.password_hash, current_password):
        record_login_attempt(ip)
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
    clear_login_attempts(ip)
    flash('تم تغيير كلمة المرور بنجاح', 'success')
    return redirect(url_for('auth.account'))


@auth_bp.route('/account/delete', methods=['POST'])
@login_required
def account_delete():
    user = g.user
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    password = request.form.get('password', '')
    if not password:
        flash('يجب إدخال كلمة المرور لتأكيد حذف الحساب', 'error')
        return redirect(url_for('auth.account'))

    if not check_password_hash(user.password_hash, password):
        record_login_attempt(get_client_ip())
        flash('كلمة المرور غير صحيحة', 'error')
        return redirect(url_for('auth.account'))

    success, msg = UserService.delete_user_fully(user.id)
    if success:
        session.clear()
        flash(msg, 'success')
        return redirect(url_for('auth.register'))
    else:
        flash(msg, 'error')
        return redirect(url_for('auth.account'))
