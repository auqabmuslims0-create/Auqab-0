from flask import render_template, request, redirect, url_for, session, flash, g, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from database import db
from models import User
from shared.repositories.user_repository import UserRepository
from shared.validators import is_valid_email, is_valid_phone_syrian, is_strong_password
from shared.security import (
    record_login_attempt,
    get_login_attempts,
    get_login_attempts_for_user,
    clear_login_attempts,
    get_client_ip,
    encrypt_session_secret,
    decrypt_session_secret,
)
from shared.utils import generate_public_id, save_image
from shared.decorators import login_required
from . import auth_bp


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    step = request.args.get('step', 1, type=int)

    # إبطال أي جلسة تسجيل قديمة (سبقت الترقية إلى 4 خطوات) — لا تحتوي على role
    # هذا يحمي المستخدمين الذين كانوا في منتصف التسجيل لحظة النشر
    if 'reg_data' in session and 'role' not in session.get('reg_data', {}):
        session.pop('reg_data', None)

    if request.method == 'POST':
        step = request.form.get('step', 1, type=int)

        # ═══ الخطوة 1: اختيار نوع الحساب ═══
        if step == 1:
            role = request.form.get('role', '')
            if role not in ['customer', 'owner']:
                flash('يرجى اختيار نوع الحساب', 'error')
                return redirect(url_for('auth.register', step=1))

            # بدء جلسة تسجيل جديدة — تنظيف أي بيانات سابقة
            session['reg_data'] = {'role': role}
            session.modified = True
            return redirect(url_for('auth.register', step=2))

        # ═══ الخطوة 2: البيانات الأساسية ═══
        elif step == 2:
            if 'reg_data' not in session or 'role' not in session['reg_data']:
                flash('يرجى البدء من الخطوة الأولى', 'error')
                return redirect(url_for('auth.register', step=1))

            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()

            if not username or not email:
                flash('جميع الحقول مطلوبة', 'error')
                return redirect(url_for('auth.register', step=2))

            if not is_valid_email(email):
                flash('البريد الإلكتروني غير صالح', 'error')
                return redirect(url_for('auth.register', step=2))

            if phone and not is_valid_phone_syrian(phone):
                flash('رقم الهاتف يجب أن يبدأ بـ 9 ويتكون من 9 أرقام', 'error')
                return redirect(url_for('auth.register', step=2))

            if UserRepository.get_by_username(username):
                flash('اسم المستخدم موجود مسبقاً', 'error')
                return redirect(url_for('auth.register', step=2))

            if UserRepository.get_by_email(email):
                flash('البريد الإلكتروني مستخدم بالفعل', 'error')
                return redirect(url_for('auth.register', step=2))

            session['reg_data']['username'] = username
            session['reg_data']['email'] = email
            session['reg_data']['phone'] = '+963' + phone if phone else None
            session.modified = True
            return redirect(url_for('auth.register', step=3))

        # ═══ الخطوة 3: كلمة المرور + الموافقة ═══
        elif step == 3:
            if 'reg_data' not in session or 'role' not in session['reg_data']:
                flash('يرجى البدء من الخطوة الأولى', 'error')
                return redirect(url_for('auth.register', step=1))

            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            agree = request.form.get('agree')

            if not password or not confirm_password:
                flash('جميع الحقول مطلوبة', 'error')
                return redirect(url_for('auth.register', step=3))

            if confirm_password != password:
                flash('كلمتا المرور غير متطابقتين', 'error')
                return redirect(url_for('auth.register', step=3))

            strong, msg = is_strong_password(password)
            if not strong:
                flash(msg, 'error')
                return redirect(url_for('auth.register', step=3))

            if not agree:
                flash('يجب الموافقة على الشروط والأحكام', 'error')
                return redirect(url_for('auth.register', step=3))

            # تشفير password_hash قبل وضعه في الجلسة — Flask sessions
            # غير مشفّرة افتراضياً، فتخزين الهاش صريحاً يعرّضه لأي XSS.
            session['reg_data']['password_hash'] = encrypt_session_secret(
                generate_password_hash(password)
            )
            session.modified = True
            return redirect(url_for('auth.register', step=4))

        # ═══ الخطوة 4: الصورة والنبذة (اختياري) + إنشاء الحساب ═══
        elif step == 4:
            if 'reg_data' not in session or 'password_hash' not in session['reg_data']:
                flash('يرجى إكمال الخطوات السابقة', 'error')
                return redirect(url_for('auth.register', step=1))

            reg = session['reg_data']

            # فك تشفير password_hash (مع دعم الجلسات القديمة غير المشفّرة)
            password_hash = decrypt_session_secret(reg.get('password_hash'))
            if not password_hash:
                flash('انتهت صلاحية جلسة التسجيل، يرجى البدء من جديد', 'error')
                session.pop('reg_data', None)
                return redirect(url_for('auth.register', step=1))

            avatar_file = request.files.get('avatar')
            bio = request.form.get('bio', '').strip()

            avatar_url = None
            if avatar_file and avatar_file.filename != '':
                try:
                    avatar_url = save_image(avatar_file)
                except ValueError as e:
                    flash(str(e), 'error')
                    return redirect(url_for('auth.register', step=4))

            user = User(
                username=reg['username'],
                email=reg['email'],
                phone=reg.get('phone'),
                password_hash=password_hash,
                role=reg['role'],
                public_id=generate_public_id(),
                avatar=avatar_url,
                bio=bio
            )
            db.session.add(user)
            db.session.commit()

            # حفظ سلة الزائر قبل session.clear() لدمجها مع DB لاحقًا
            pre_register_cart = session.get('cart', {})

            # إعادة توليد الجلسة بعد التسجيل — يمنع أي fixation (نفس سلوك login)
            session.clear()
            session['user_id'] = user.id
            session['role'] = user.role
            session['new_public_id'] = user.public_id
            session.permanent = True

            # دمج سلة الزائر (إن وُجدت) مع DB — كانت مكتسبة من localStorage
            if pre_register_cart:
                try:
                    from shared.services.cart_service import CartService
                    merged = CartService.merge_session_with_db(user.id, pre_register_cart)
                    db.session.commit()
                    if merged:
                        session['cart'] = merged
                except Exception as e:
                    db.session.rollback()
                    current_app.logger.error(
                        f'فشل دمج سلة التسجيل للمستخدم {user.id}: {e}'
                    )

            return redirect(url_for('auth.show_public_id'))

    # حرّاس GET — التوجيه حسب حالة الجلسة
    if step == 2 and ('reg_data' not in session or 'role' not in session.get('reg_data', {})):
        return redirect(url_for('auth.register', step=1))
    if step == 3 and ('reg_data' not in session or 'role' not in session.get('reg_data', {})):
        return redirect(url_for('auth.register', step=1))
    if step == 4 and ('reg_data' not in session or 'password_hash' not in session['reg_data']):
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
    if 'user_id' in session and g.user:
        return redirect(url_for('auth.dashboard'))

    login_error = None
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip()
        password = request.form.get('password', '')
        remember_me = request.form.get('remember_me') == '1'

        ip = get_client_ip()

        # القيد الأول: 5 محاولات لكل IP خلال 5 دقائق (يحمي شبكات NAT المشتركة)
        if get_login_attempts(ip) >= 5:
            flash('تم تجاوز عدد المحاولات المسموح، حاول بعد 5 دقائق', 'danger')
            return render_template('auth/login.html', login_error=None)

        user = User.query.filter(
            (User.username == login_id) | (User.email == login_id)
        ).first()

        # القيد الثاني: 15 محاولة لهذا المستخدم عبر جميع الـ IPs
        # يحمي من هجمات IP rotation على حساب محدد
        if user and get_login_attempts_for_user(user.id) >= 15:
            flash('تم تجاوز عدد المحاولات المسموح لهذا الحساب، حاول بعد 15 دقيقة', 'danger')
            return render_template('auth/login.html', login_error=None)

        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash('الحساب محظور، يرجى التواصل مع الإدارة', 'danger')
                return render_template('auth/login.html', login_error=None)

            # حفظ سلة الزائر قبل session.clear()
            pre_login_cart = session.get('cart', {})

            session.clear()
            session['user_id'] = user.id
            session['role'] = user.role
            session.permanent = True
            clear_login_attempts(ip)

            # دمج سلة الزائر مع DB فورًا — بدل تأجيلها حتى زيارة /cart
            if pre_login_cart:
                try:
                    from shared.services.cart_service import CartService
                    merged = CartService.merge_session_with_db(user.id, pre_login_cart)
                    db.session.commit()
                    if merged:
                        session['cart'] = merged
                except Exception as e:
                    db.session.rollback()
                    current_app.logger.error(
                        f'فشل دمج السلة عند تسجيل الدخول للمستخدم {user.id}: {e}'
                    )

            flash('تم تسجيل الدخول', 'success')
            return redirect(url_for('auth.dashboard'))
        else:
            # ربط المحاولة بـ user_id إن وُجد — يُمكّن القيد الثاني أعلاه
            record_login_attempt(ip, user_id=user.id if user else None)
            return render_template('auth/login.html', login_error='بيانات الدخول غير صحيحة، يرجى التحقق والمحاولة مرة أخرى.')

    return render_template('auth/login.html', login_error=login_error)


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    # POST فقط — منع هجوم "logout via <img src=/logout>" من صفحات خارجية.
    # الأزرار في القوالب تحتاج form مع csrf_token (تحدَّث في base.html).
    session.clear()
    flash('تم تسجيل الخروج', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/dashboard')
@login_required
def dashboard():
    user = g.user
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
