from flask import render_template, request, redirect, url_for, flash, abort
from database import db
from models import User, Order
from shared.services.delivery_service import DeliveryService
from shared.validators import is_valid_email, is_strong_password, is_valid_phone_syrian
from shared.utils import generate_public_id
from werkzeug.security import generate_password_hash
from shared.decorators import role_required
from . import admin_bp

@admin_bp.route('/admin/delivery_persons')
@role_required('admin')
def admin_delivery_persons():
    persons = User.query.filter_by(role='delivery').order_by(User.username).all()

    for person in persons:
        if not person.is_active:
            person.availability_label = 'محظور'
            person.availability_color = 'danger'
        else:
            from shared.time_utils import current_time
            now_time = current_time().time()
            if person.shift_start_time and person.shift_end_time:
                if person.shift_start_time < person.shift_end_time:
                    in_shift = person.shift_start_time <= now_time < person.shift_end_time
                else:
                    in_shift = now_time >= person.shift_start_time or now_time < person.shift_end_time
            else:
                in_shift = True

            if not in_shift:
                person.availability_label = 'خارج الوردية'
                person.availability_color = 'secondary'
            else:
                active_count = Order.query.filter(
                    Order.delivery_person_id == person.id,
                    Order.status.in_(['ready', 'delivering'])
                ).count()
                max_orders = person.max_active_orders if person.max_active_orders and person.max_active_orders > 0 else 0
                if max_orders == 0 or active_count >= max_orders:
                    person.availability_label = 'مشغول'
                    person.availability_color = 'warning text-dark'
                else:
                    person.availability_label = 'متاح الآن'
                    person.availability_color = 'success'

    return render_template('admin/admin_delivery_persons.html', persons=persons)

@admin_bp.route('/admin/delivery_persons/<int:user_id>/shift', methods=['GET', 'POST'])
@role_required('admin')
def admin_delivery_shift_edit(user_id):
    person = User.query.get_or_404(user_id)
    if person.role != 'delivery':
        abort(403)

    if request.method == 'POST':
        start_time_str = request.form.get('shift_start_time')
        end_time_str = request.form.get('shift_end_time')
        max_active = request.form.get('max_active_orders', type=int, default=3)

        success, msg = DeliveryService.update_shift(user_id, start_time_str, end_time_str, max_active)
        flash(msg, 'success' if success else 'error')
        return redirect(url_for('admin.admin_delivery_persons'))

    return render_template('admin/admin_delivery_shift_form.html', person=person)

@admin_bp.route('/admin/delivery_persons/new', methods=['GET', 'POST'])
@role_required('admin')
def admin_delivery_person_new():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')

        if not username or not email or not password:
            flash('اسم المستخدم والبريد وكلمة المرور مطلوبة', 'error')
            return redirect(url_for('admin.admin_delivery_person_new'))

        if User.query.filter_by(username=username).first():
            flash('اسم المستخدم موجود مسبقاً', 'error')
            return redirect(url_for('admin.admin_delivery_person_new'))

        if User.query.filter_by(email=email).first():
            flash('البريد الإلكتروني مستخدم بالفعل', 'error')
            return redirect(url_for('admin.admin_delivery_person_new'))

        if not is_valid_email(email):
            flash('البريد الإلكتروني غير صالح', 'error')
            return redirect(url_for('admin.admin_delivery_person_new'))

        if phone and not is_valid_phone_syrian(phone):
            flash('رقم الهاتف يجب أن يبدأ بـ 9 ويتكون من 9 أرقام', 'error')
            return redirect(url_for('admin.admin_delivery_person_new'))

        strong, msg = is_strong_password(password)
        if not strong:
            flash(msg, 'error')
            return redirect(url_for('admin.admin_delivery_person_new'))

        full_phone = '+963' + phone if phone else ''
        public_id = generate_public_id()

        delivery_user = User(
            username=username,
            email=email,
            phone=full_phone,
            password_hash=generate_password_hash(password),
            role='delivery',
            is_available=True,
            public_id=public_id
        )
        try:
            db.session.add(delivery_user)
            db.session.commit()
            flash('تم إضافة المندوب بنجاح', 'success')
            return redirect(url_for('admin.admin_delivery_persons'))
        except Exception:
            db.session.rollback()
            flash('حدث خطأ أثناء إضافة المندوب', 'error')
            return redirect(url_for('admin.admin_delivery_person_new'))

    return render_template('admin/admin_delivery_person_form.html', person=None)

@admin_bp.route('/admin/delivery_persons/<int:user_id>/edit', methods=['GET', 'POST'])
@role_required('admin')
def admin_delivery_person_edit(user_id):
    person = User.query.get_or_404(user_id)
    if person.role != 'delivery':
        abort(403)

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')

        if not username or not email:
            flash('اسم المستخدم والبريد مطلوبان', 'error')
            return redirect(url_for('admin.admin_delivery_person_edit', user_id=person.id))

        existing_username = User.query.filter(User.username == username, User.id != person.id).first()
        if existing_username:
            flash('اسم المستخدم موجود مسبقاً', 'error')
            return redirect(url_for('admin.admin_delivery_person_edit', user_id=person.id))

        existing_email = User.query.filter(User.email == email, User.id != person.id).first()
        if existing_email:
            flash('البريد الإلكتروني مستخدم بالفعل', 'error')
            return redirect(url_for('admin.admin_delivery_person_edit', user_id=person.id))

        if not is_valid_email(email):
            flash('البريد الإلكتروني غير صالح', 'error')
            return redirect(url_for('admin.admin_delivery_person_edit', user_id=person.id))

        if phone and not is_valid_phone_syrian(phone):
            flash('رقم الهاتف يجب أن يبدأ بـ 9 ويتكون من 9 أرقام', 'error')
            return redirect(url_for('admin.admin_delivery_person_edit', user_id=person.id))

        person.username = username
        person.email = email
        if phone:
            person.phone = '+963' + phone
        else:
            person.phone = None

        if password:
            strong, msg = is_strong_password(password)
            if not strong:
                flash(msg, 'error')
                return redirect(url_for('admin.admin_delivery_person_edit', user_id=person.id))
            person.password_hash = generate_password_hash(password)

        try:
            db.session.commit()
            flash('تم حفظ تعديلات المندوب', 'success')
            return redirect(url_for('admin.admin_delivery_persons'))
        except Exception:
            db.session.rollback()
            flash('حدث خطأ أثناء حفظ التعديلات', 'error')
            return redirect(url_for('admin.admin_delivery_person_edit', user_id=person.id))

    return render_template('admin/admin_delivery_person_form.html', person=person)

@admin_bp.route('/admin/delivery_persons/<int:user_id>/toggle', methods=['POST'])
@role_required('admin')
def admin_delivery_person_toggle(user_id):
    success, msg, _ = DeliveryService.toggle_delivery_person(user_id)
    flash(msg, 'success' if success else 'error')
    return redirect(url_for('admin.admin_delivery_persons'))

@admin_bp.route('/admin/delivery_persons/<int:user_id>/delete', methods=['POST'])
@role_required('admin')
def admin_delivery_person_delete(user_id):
    success, msg = DeliveryService.delete_delivery_person(user_id)
    flash(msg, 'success' if success else 'error')
    return redirect(url_for('admin.admin_delivery_persons'))
