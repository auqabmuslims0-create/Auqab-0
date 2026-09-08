from flask import render_template, request, redirect, url_for, flash, abort, session
from database import db
from models import User, Store, Product, Order, Category, Reel, Subscription, Review, ProductComment, ProductReaction
from sqlalchemy import func
from shared.time_utils import current_time
from shared.utils import is_store_active, save_image, get_setting
from shared.validators import is_valid_phone_syrian
from shared.decorators import role_required
from . import store_bp
from .common import check_store_access

@store_bp.route('/my_stores')
@role_required('owner')
def my_stores():
    user = db.session.get(User, session['user_id'])
    from shared.services.subscription_service import SubscriptionService
    SubscriptionService.check_expiring_subscriptions()

    stores = Store.query.filter_by(owner_id=user.id).all()
    return render_template('store_owner/my_stores.html', stores=stores)

@store_bp.route('/store/new', methods=['GET', 'POST'])
@role_required('owner')
def new_store():
    user = db.session.get(User, session['user_id'])
    step = request.args.get('step', 1, type=int)

    if request.method == 'POST':
        step = request.form.get('step', 1, type=int)

        if step == 1:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            phone = request.form.get('phone', '').strip()

            if not name:
                flash('اسم المتجر مطلوب', 'error')
                return redirect(url_for('store.new_store', step=1))

            if phone and not is_valid_phone_syrian(phone):
                flash('رقم الهاتف يجب أن يبدأ بـ 9 ويتكون من 9 أرقام', 'error')
                return redirect(url_for('store.new_store', step=1))

            logo_file = request.files.get('logo')
            logo_filename = save_image(logo_file) if logo_file and logo_file.filename != '' else None

            session['store_temp'] = {
                'name': name,
                'description': description,
                'phone': '+963' + phone if phone else '',
                'logo_url': logo_filename
            }
            return redirect(url_for('store.new_store', step=2))

        elif step == 2:
            if 'store_temp' not in session:
                flash('يرجى البدء من الخطوة الأولى', 'error')
                return redirect(url_for('store.new_store', step=1))

            address = request.form.get('address', '').strip()
            latitude = request.form.get('latitude', type=float)
            longitude = request.form.get('longitude', type=float)

            session['store_temp']['address'] = address
            session['store_temp']['latitude'] = latitude
            session['store_temp']['longitude'] = longitude
            session.modified = True
            return redirect(url_for('store.new_store', step=3))

        elif step == 3:
            if 'store_temp' not in session:
                flash('يرجى البدء من الخطوة الأولى', 'error')
                return redirect(url_for('store.new_store', step=1))

            opening_time = request.form.get('opening_time', '').strip()
            closing_time = request.form.get('closing_time', '').strip()
            has_delivery = request.form.get('has_delivery') == 'yes'

            working_hours = f"{opening_time} - {closing_time}" if opening_time and closing_time else ''

            data = session['store_temp']
            store = Store(
                owner_id=user.id,
                name=data['name'],
                description=data.get('description', ''),
                logo_url=data.get('logo_url'),
                phone=data.get('phone', ''),
                address=data.get('address', ''),
                working_hours=working_hours,
                has_delivery=has_delivery,
                latitude=data.get('latitude'),
                longitude=data.get('longitude'),
                subscription_status='pending'
            )
            db.session.add(store)
            db.session.commit()

            session.pop('store_temp', None)
            flash('تم إنشاء المتجر، يرجى اختيار طريقة الدفع لتفعيل الاشتراك', 'success')
            return redirect(url_for('store.store_subscription', store_id=store.id))

    if step > 1 and 'store_temp' not in session:
        return redirect(url_for('store.new_store', step=1))

    return render_template('store_owner/new_store.html', step=step)

@store_bp.route('/store/<int:store_id>')
@role_required('owner')
def store_manage(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    if store.subscription_status == 'suspended':
        wallet_number = get_setting('wallet_number', '0995680223')
        contact_phone = '+963' + wallet_number[1:] if wallet_number.startswith('0') else wallet_number
        return render_template('store_owner/store_suspended.html', store=store, contact_phone=contact_phone)

    if store.subscription_status != 'active':
        flash('هذا المتجر غير نشط، يجب دفع الاشتراك')
        return redirect(url_for('store.store_subscription', store_id=store.id))

    products_count = Product.query.filter_by(store_id=store.id).count()
    orders_count = Order.query.filter_by(store_id=store.id).count()
    categories_count = Category.query.filter_by(store_id=store.id).count()
    reels_count = Reel.query.filter_by(store_id=store.id).count()
    total_revenue = db.session.query(func.sum(Order.total)).filter(
        Order.store_id == store.id,
        Order.status != 'cancelled'
    ).scalar() or 0

    products_ids = [p.id for p in store.products]
    if products_ids:
        reviews_count = Review.query.filter(Review.product_id.in_(products_ids)).count()
        comments_count = ProductComment.query.filter(ProductComment.product_id.in_(products_ids)).count()
        reactions_count = ProductReaction.query.filter(ProductReaction.product_id.in_(products_ids)).count()
    else:
        reviews_count = comments_count = reactions_count = 0

    views_count = db.session.query(func.sum(Product.views)).filter(
        Product.store_id == store.id
    ).scalar() or 0

    paid_sub = Subscription.query.filter_by(store_id=store.id, status='paid') \
        .order_by(Subscription.end_date.desc()).first()

    return render_template('store_owner/store_manage.html',
                           store=store,
                           subscription=paid_sub,
                           products_count=products_count,
                           orders_count=orders_count,
                           categories_count=categories_count,
                           reels_count=reels_count,
                           total_revenue=total_revenue,
                           reviews_count=reviews_count,
                           comments_count=comments_count,
                           reactions_count=reactions_count,
                           views_count=views_count)
