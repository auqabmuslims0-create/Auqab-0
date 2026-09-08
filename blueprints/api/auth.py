from flask import request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from database import db
from models import User
from shared.validators import is_strong_password, is_valid_email, is_valid_phone_syrian
from shared.utils import generate_public_id
from shared.security import record_login_attempt, get_login_attempts, clear_login_attempts
from sqlalchemy import or_
from . import api_bp
from .helpers import encode_auth_token, token_required, serialize_user

@api_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'message': 'يجب إرسال البيانات بصيغة JSON'}), 400

    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'customer')

    if not username or not email or not password:
        return jsonify({'message': 'اسم المستخدم والبريد وكلمة المرور مطلوبة'}), 400

    if role not in ['customer', 'owner']:
        role = 'customer'

    strong, msg = is_strong_password(password)
    if not strong:
        return jsonify({'message': msg}), 400

    if not is_valid_email(email):
        return jsonify({'message': 'البريد الإلكتروني غير صالح'}), 400

    if phone and not is_valid_phone_syrian(phone):
        return jsonify({'message': 'رقم الهاتف يجب أن يبدأ بـ 9 ويتكون من 9 أرقام'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'message': 'اسم المستخدم موجود مسبقاً'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'message': 'البريد الإلكتروني مستخدم بالفعل'}), 400

    full_phone = '+963' + phone if phone else ''
    public_id = generate_public_id()

    user = User(
        username=username,
        email=email,
        phone=full_phone,
        password_hash=generate_password_hash(password),
        role=role,
        public_id=public_id
    )
    try:
        db.session.add(user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'حدث خطأ أثناء إنشاء الحساب'}), 500

    token = encode_auth_token(user.id)
    return jsonify({
        'message': 'تم إنشاء الحساب بنجاح',
        'token': token,
        'user': serialize_user(user)
    }), 201

@api_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'message': 'يجب إرسال البيانات بصيغة JSON'}), 400

    login_id = data.get('login_id', '').strip()
    password = data.get('password', '')

    if not login_id or not password:
        return jsonify({'message': 'اسم المستخدم/البريد وكلمة المرور مطلوبان'}), 400

    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip:
        ip = ip.split(',')[0].strip()

    if get_login_attempts(ip) >= 5:
        return jsonify({'message': 'تم تجاوز عدد المحاولات المسموح، حاول بعد 5 دقائق'}), 429

    user = User.query.filter(
        or_(User.username == login_id, User.email == login_id)
    ).first()

    if user and check_password_hash(user.password_hash, password):
        if not user.is_active:
            return jsonify({'message': 'هذا الحساب موقوف'}), 403
        clear_login_attempts(ip)
        token = encode_auth_token(user.id)
        return jsonify({
            'message': 'تم تسجيل الدخول',
            'token': token,
            'user': serialize_user(user)
        }), 200
    else:
        record_login_attempt(ip)
        return jsonify({'message': 'بيانات الدخول غير صحيحة'}), 401

@api_bp.route('/me', methods=['GET'])
@token_required
def get_me(current_user):
    return jsonify({'user': serialize_user(current_user)}), 200

@api_bp.route('/me', methods=['PUT'])
@token_required
def update_me(current_user):
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'message': 'يجب إرسال البيانات بصيغة JSON'}), 400

    username = data.get('username', current_user.username).strip()
    email = data.get('email', current_user.email).strip()
    phone = data.get('phone', current_user.phone or '').strip()

    if not username or not email:
        return jsonify({'message': 'اسم المستخدم والبريد الإلكتروني مطلوبان'}), 400

    if not is_valid_email(email):
        return jsonify({'message': 'البريد الإلكتروني غير صالح'}), 400

    existing_username = User.query.filter(
        User.username == username, User.id != current_user.id
    ).first()
    if existing_username:
        return jsonify({'message': 'اسم المستخدم موجود مسبقاً'}), 400

    existing_email = User.query.filter(
        User.email == email, User.id != current_user.id
    ).first()
    if existing_email:
        return jsonify({'message': 'البريد الإلكتروني مستخدم بالفعل'}), 400

    if phone:
        if not is_valid_phone_syrian(phone):
            return jsonify({'message': 'رقم الهاتف يجب أن يبدأ بـ 9 ويتكون من 9 أرقام'}), 400
        current_user.phone = '+963' + phone
    else:
        current_user.phone = None

    current_user.username = username
    current_user.email = email

    try:
        db.session.commit()
        return jsonify({'message': 'تم تحديث بيانات الحساب بنجاح', 'user': serialize_user(current_user)}), 200
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'حدث خطأ أثناء تحديث البيانات'}), 500

@api_bp.route('/me/change_password', methods=['POST'])
@token_required
def change_password(current_user):
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'message': 'يجب إرسال البيانات بصيغة JSON'}), 400

    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')

    if not current_password or not new_password or not confirm_password:
        return jsonify({'message': 'جميع الحقول مطلوبة'}), 400

    if not check_password_hash(current_user.password_hash, current_password):
        return jsonify({'message': 'كلمة المرور الحالية غير صحيحة'}), 400

    if new_password != confirm_password:
        return jsonify({'message': 'كلمتا المرور غير متطابقتين'}), 400

    strong, msg = is_strong_password(new_password)
    if not strong:
        return jsonify({'message': msg}), 400

    current_user.password_hash = generate_password_hash(new_password)
    try:
        db.session.commit()
        return jsonify({'message': 'تم تغيير كلمة المرور بنجاح'}), 200
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'حدث خطأ أثناء تغيير كلمة المرور'}), 500

@api_bp.route('/me/verify_password', methods=['POST'])
@token_required
def verify_password(current_user):
    data = request.get_json(silent=True) or {}
    password = data.get('password', '')
    if not password:
        return jsonify({'message': 'كلمة المرور مطلوبة'}), 400
    if check_password_hash(current_user.password_hash, password):
        return jsonify({'message': 'تم التحقق', 'valid': True}), 200
    return jsonify({'message': 'كلمة المرور غير صحيحة', 'valid': False}), 400

@api_bp.route('/me/avatar', methods=['POST'])
@token_required
def upload_avatar(current_user):
    file = request.files.get('avatar')
    if not file:
        return jsonify({'message': 'لم يتم إرسال ملف'}), 400
    from shared.utils import save_image
    saved_name = save_image(file)
    if saved_name:
        current_user.avatar = saved_name
        db.session.commit()
        return jsonify({'message': 'تم تحديث الصورة الشخصية', 'user': serialize_user(current_user)}), 200
    return jsonify({'message': 'فشل رفع الملف'}), 500

@api_bp.route('/me/delete', methods=['POST'])
@token_required
def delete_me(current_user):
    from shared.services.user_service import UserService
    try:
        success, msg = UserService.delete_user_fully(current_user.id)
        if not success:
            return jsonify({'message': msg}), 400
        return jsonify({'message': msg}), 200
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'حدث خطأ أثناء حذف الحساب'}), 500
