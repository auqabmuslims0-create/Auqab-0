from shared.validators import is_valid_phone_syrian
from flask import render_template, request, redirect, url_for, flash, abort
from sqlalchemy.orm import joinedload
from database import db
from models import Product, Review
import os
from datetime import timedelta
from shared.time_utils import current_time
from shared.utils import save_image, get_upload_path, delete_local_file
from shared.decorators import role_required
from . import store_bp
from .common import check_store_access

@store_bp.route('/store/<int:store_id>/edit', methods=['GET', 'POST'])
@role_required('owner')
def edit_store(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    if request.method == 'POST':
        store.name = request.form.get('name', '').strip()
        store.description = request.form.get('description', '').strip()
        phone = request.form.get('phone', '').strip()
        store.address = request.form.get('address', '').strip()
        opening_time = request.form.get('opening_time', '').strip()
        closing_time = request.form.get('closing_time', '').strip()
        has_delivery = request.form.get('has_delivery') == 'yes'
        store.latitude = request.form.get('latitude', type=float)
        store.longitude = request.form.get('longitude', type=float)

        if not store.name:
            flash('اسم المتجر لا يمكن أن يكون فارغاً')
            return redirect(url_for('store.edit_store', store_id=store.id))

        if phone and not is_valid_phone_syrian(phone):
            flash('رقم الهاتف يجب أن يبدأ بـ 9 ويتكون من 9 أرقام')
            return redirect(url_for('store.edit_store', store_id=store.id))

        store.phone = '+963' + phone if phone else ''
        store.working_hours = f"{opening_time} - {closing_time}" if opening_time and closing_time else ''

        logo_file = request.files.get('logo')
        if logo_file and logo_file.filename != '':
            old_logo_url = store.logo_url
            new_logo = save_image(logo_file, old_url=old_logo_url)
            if new_logo:
                store.logo_url = new_logo
            else:
                flash('فشل رفع الشعار', 'error')
                return redirect(url_for('store.edit_store', store_id=store.id))

        store.has_delivery = has_delivery
        db.session.commit()
        flash('تم حفظ التعديلات')
        return redirect(url_for('store.store_manage', store_id=store.id))

    pending_deletion_at_iso = store.pending_deletion_at.isoformat() if store.pending_deletion_at else None
    return render_template('store_owner/edit_store.html', store=store,
                           pending_deletion_at_iso=pending_deletion_at_iso)

@store_bp.route('/store/<int:store_id>/request_delete', methods=['POST'])
@role_required('owner')
def request_delete_store(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result
    store.pending_deletion_at = current_time() + timedelta(hours=48)
    db.session.commit()
    flash('تمت جدولة حذف المتجر خلال 48 ساعة. يمكنك التراجع قبل انتهاء المدة.', 'warning')
    return redirect(url_for('store.edit_store', store_id=store.id))

@store_bp.route('/store/<int:store_id>/cancel_delete', methods=['POST'])
@role_required('owner')
def cancel_delete_store(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result
    store.pending_deletion_at = None
    db.session.commit()
    flash('تم إلغاء طلب الحذف.', 'success')
    return redirect(url_for('store.edit_store', store_id=store.id))

@store_bp.route('/store/<int:store_id>/comments')
@role_required('owner')
def store_comments(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    reviews = Review.query.join(
        Product, Review.product_id == Product.id
    ).filter(
        Product.store_id == store.id,
        Review.comment.isnot(None),
        Review.comment != ''
    ).options(
        joinedload(Review.user),
        joinedload(Review.product)
    ).order_by(Review.created_at.desc()).all()

    grouped = {}
    for review in reviews:
        pid = review.product_id
        if pid not in grouped:
            grouped[pid] = {
                'product': review.product,
                'reviews': []
            }
        grouped[pid]['reviews'].append(review)

    return render_template('store_owner/store_comments.html', store=store, grouped=grouped)
