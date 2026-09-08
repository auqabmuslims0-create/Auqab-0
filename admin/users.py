from flask import render_template, request, redirect, url_for, session, flash, abort
from sqlalchemy import func, or_
from database import db
from models import User, Order, Store, Favorite, Review, ProductComment
from shared.services.user_service import UserService
from shared.decorators import role_required
from . import admin_bp

@admin_bp.route('/admin/users')
@role_required('admin')
def admin_users():
    role_filter = request.args.get('role', '').strip()
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20
    temp_password = session.pop('reset_password_temp', None)

    query = User.query

    if role_filter in ['admin', 'owner', 'customer', 'delivery']:
        query = query.filter_by(role=role_filter)
    if q:
        query = query.filter(
            or_(
                User.username.ilike(f'%{q}%'),
                User.email.ilike(f'%{q}%'),
                User.phone.ilike(f'%{q}%')
            )
        )

    pagination = query.order_by(User.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    users = pagination.items

    user_stats = {}
    if users:
        user_ids = [u.id for u in users]
        customer_counts = dict(db.session.query(
            Order.customer_id, func.count(Order.id)
        ).filter(Order.customer_id.in_(user_ids)).group_by(Order.customer_id).all())

        store_counts = dict(db.session.query(
            Store.owner_id, func.count(Store.id)
        ).filter(Store.owner_id.in_(user_ids)).group_by(Store.owner_id).all())

        delivery_counts = dict(db.session.query(
            Order.delivery_person_id, func.count(Order.id)
        ).filter(Order.delivery_person_id.in_(user_ids)).group_by(Order.delivery_person_id).all())

        favorite_counts = dict(db.session.query(
            Favorite.user_id, func.count(Favorite.id)
        ).filter(Favorite.user_id.in_(user_ids)).group_by(Favorite.user_id).all())

        review_counts = dict(db.session.query(
            Review.user_id, func.count(Review.id)
        ).filter(Review.user_id.in_(user_ids)).group_by(Review.user_id).all())

        comment_counts = dict(db.session.query(
            ProductComment.user_id, func.count(ProductComment.id)
        ).filter(ProductComment.user_id.in_(user_ids)).group_by(ProductComment.user_id).all())

        for u in users:
            user_stats[u.id] = {
                'orders_count': customer_counts.get(u.id, 0),
                'stores_count': store_counts.get(u.id, 0),
                'delivery_count': delivery_counts.get(u.id, 0),
                'favorites_count': favorite_counts.get(u.id, 0),
                'reviews_count': review_counts.get(u.id, 0),
                'comments_count': comment_counts.get(u.id, 0),
            }

    return render_template('admin/admin_users.html',
                           users=users,
                           pagination=pagination,
                           role_filter=role_filter,
                           q=q,
                           temp_password=temp_password,
                           user_stats=user_stats)

@admin_bp.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@role_required('admin')
def admin_toggle_user(user_id):
    admin_user = db.session.get(User, session['user_id'])
    success, msg, _ = UserService.toggle_user_status(user_id, admin_user_id=admin_user.id)
    flash(msg, 'success' if success else 'error')
    return redirect(url_for('admin.admin_users'))

@admin_bp.route('/admin/users/<int:user_id>/reset_password', methods=['POST'])
@role_required('admin')
def admin_reset_password(user_id):
    success, msg, temp_password = UserService.reset_password(user_id)
    if success:
        session['reset_password_temp'] = temp_password
        flash(f'{msg}. كلمة المرور المؤقتة: {temp_password}', 'success')
    else:
        flash(msg, 'error')
    return redirect(url_for('admin.admin_users'))

@admin_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@role_required('admin')
def admin_delete_user(user_id):
    admin_user = db.session.get(User, session['user_id'])
    success, msg = UserService.delete_user_fully(user_id, admin_user_id=admin_user.id)
    flash(msg, 'success' if success else 'error')
    return redirect(url_for('admin.admin_users'))

@admin_bp.route('/admin/users/<int:user_id>/contact', methods=['GET', 'POST'])
@role_required('admin')
def admin_contact_user(user_id):
    target_user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        message = request.form.get('message', '').strip()
        if not title or not message:
            flash('العنوان والموضوع مطلوبان', 'error')
            return redirect(url_for('admin.admin_contact_user', user_id=target_user.id))

        from shared.services.notification_service import NotificationService
        NotificationService.send_to_user(
            user_id=target_user.id,
            title=title,
            message=message,
            link=None,
            type_=NotificationService.TYPE_MESSAGE
        )
        db.session.commit()
        flash('تم إرسال الرسالة بنجاح', 'success')
        return redirect(url_for('admin.admin_users'))

    return render_template('admin/admin_contact_user.html', target_user=target_user)
