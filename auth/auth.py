import os
from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from database import db
from models import User
from shared.repositories.user_repository import UserRepository
from shared.validators import is_valid_email, is_valid_phone_syrian, is_strong_password
from shared.security import record_login_attempt, get_login_attempts, clear_login_attempts
from shared.utils import generate_public_id, save_image
from shared.decorators import login_required
from . import auth_bp

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    step = request.args.get('step', 1, type=int)

    if request.method == 'POST':
        step = request.form.get('step', 1, type=int)

        if step == 1:
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()

            if not username or not email:
                flash('جميع الحقول مطلوبة', 'error')
                return redirect(url_for('auth.register', step=1))

            if not is_valid_email(email):
                flash('البريد الإلكتروني غير صالح', 'error')
                return redirect(url_for('auth.register', step=1))

            if phone and not is_valid_phone_syrian(phone):
                flash('رقم الهاتف يجب أن يبدأ بـ 9 ويتكون من 9 أرقام', 'error')
                return redirect(url_for('auth.register', step=1))

            if UserRepository.get_by_username(username):
                flash('اسم المستخدم موجود مسبقاً', 'error')
                return redirect(url_for('auth.register', step=1))

            if UserRepository.get_by_email(email):
                flash('البريد الإلكتروني مستخدم بالفعل', 'error')
                return redirect(url_for('auth.register', step=1))

            session['reg_data'] = {
                'username': username,
                'email': email,
                'phone': '+963' + phone if phone else ''
            }
            return redirect(url_for('auth.register', step=2))

        elif step == 2:
            if 'reg_data' not in session:
                flash('يرجى البدء من الخطوة الأولى', 'error')
                return redirect(url_for('auth.register', step=1))

            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            role = request.form.get('role', 'customer')
            agree = request.form.get('agree')

            if not password or not confirm_password:
                flash('جميع الحقول مطلوبة', 'error')
                return redirect(url_for('auth.register', step=2))

            if confirm_password != password:
                flash('كلمتا المرور غير متطابقتين', 'error')
                return redirect(url_for('auth.register', step=2))

            strong, msg = is_strong_password(password)
            if not strong:
                flash(msg, 'error')
                return redirect(url_for('auth.register', step=2))

            if not agree:
                flash('يجب الموافقة على الشروط والأحكام', 'error')
                return redirect(url_for('auth.register', step=2))

            if role not in ['customer', 'owner']:
                role = 'customer'

            session['reg_data']['password'] = password
            session['reg_data']['role'] = role
            session.modified = True
            return redirect(url_for('auth.register', step=3))

        elif step == 3:
            if 'reg_data' not in session or 'password' not in session['reg_data']:
                flash('يرجى إكمال الخطوات السابقة', 'error')
                return redirect(url_for('auth.register', step=1))

            reg = session['reg_data']
            avatar_file = request.files.get('avatar')
            bio = request.form.get('bio', '').strip()

            avatar_url = None
            if avatar_file and avatar_file.filename != '':
                avatar_file.seek(0, os.SEEK_END)
                file_size = avatar_file.tell()
                avatar_file.seek(0)

                if file_size > 10 * 1024 * 1024:
                    flash('حجم الصورة كبير جداً (الحد الأقصى 10MB)', 'error')
                    return redirect(url_for('auth.register', step=3))

                try:
                    avatar_url = save_image(avatar_file)
                except Exception as e:
                    flash(str(e), 'error')
                    return redirect(url_for('auth.register', step=3))

            user = User(
                username=reg['username'],
                email=reg['email'],
                phone=reg.get('phone'),
                password_hash=generate_password_hash(reg['password']),
                role=reg['role'],
                public_id=generate_public_id(),
                avatar=avatar_url,
                bio=bio
            )
            db.session.add(user)
            db.session.commit()

            session.pop('reg_data', None)
            session.clear()
            session['user_id'] = user.id
            session['role'] = user.role
            session['new_public_id'] = user.public_id
            # تم حذف تعيين _csrf_token يدويًا (يتم توليده تلقائيًا عبر Flask-WTF)
            return redirect(url_for('auth.show_public_id'))

    if step == 2 and 'reg_data' not in session:
        return redirect(url_for('auth.register', step=1))
    if step == 3 and ('reg_data' not in session or 'password' not in session['reg_data']):
        return redirect(url_for('auth.register', step=1))

    return render_template('auth/register.html', step=step)

@auth_bp.route('/show_public_id')
def show_public_id():
    if 'user_id' not in session or 'new_public_id' not in session:
        flash('لا يوجد معرف جديد', 'error')
        return redirect(url_for('auth.login'))
    public_id = session.pop('new_public_id')
    return render_template('auth/show_public_id.html', public_id=public_id)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        user = db.session.get(User, session['user_id'])
        if user:
            return redirect(url_for('auth.dashboard'))

    login_error = None
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        password = request.form.get('password', '')
        remember_me = request.form.get('remember_me') == '1'

        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip:
            ip = ip.split(',')[0].strip()

        if get_login_attempts(ip) >= 5:
            flash('تم تجاوز عدد المحاولات المسموح، حاول بعد 5 دقائق', 'danger')
            return render_template('auth/login.html', login_error=None)

        user = User.query.filter(
            (User.username == login_id) | (User.email == login_id)
        ).first()

        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash('الحساب محظور، يرجى التواصل مع الإدارة', 'danger')
                return render_template('auth/login.html', login_error=None)

            session.clear()
            session['user_id'] = user.id
            session['role'] = user.role
            # تم حذف تعيين _csrf_token يدويًا (يتم توليده تلقائيًا عبر Flask-WTF)
            clear_login_attempts(ip)

            if remember_me:
                session.permanent = True

            flash('تم تسجيل الدخول', 'success')
            return redirect(url_for('auth.dashboard'))
        else:
            record_login_attempt(ip)
            return render_template('auth/login.html', login_error='بيانات الدخول غير صحيحة، يرجى التحقق والمحاولة مرة أخرى.')

    return render_template('auth/login.html', login_error=login_error)

@auth_bp.route('/logout')
@login_required
def logout():
    session.clear()
    flash('تم تسجيل الخروج', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/dashboard')
@login_required
def dashboard():
    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    if user.role == 'admin':
        return redirect(url_for('admin.admin_dashboard'))
    elif user.role == 'owner':
        return redirect(url_for('store.my_stores'))
    elif user.role == 'delivery':
        return redirect(url_for('delivery.delivery_dashboard'))
    else:
        return redirect(url_for('market.market'))
