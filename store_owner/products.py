from flask import render_template, request, redirect, url_for, flash, abort
from database import db
from models import Product, Category, Reel
import os
from sqlalchemy.orm import joinedload
from shared.utils import is_store_active, save_image, save_video, delete_local_file
from shared.decorators import role_required
from . import store_bp
from .common import check_store_access

@store_bp.route('/store/<int:store_id>/products')
@role_required('owner')
def store_products(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    q = request.args.get('q', '').strip()
    category_id = request.args.get('category_id', type=int)

    query = Product.query.filter_by(store_id=store.id).options(joinedload(Product.category))
    if q:
        query = query.filter(Product.name.ilike(f'%{q}%'))
    if category_id:
        query = query.filter_by(category_id=category_id)

    products = query.order_by(Product.created_at.desc()).all()
    categories = Category.query.filter_by(store_id=store.id).all()
    total_products_value = sum(p.price if p.price is not None else 0 for p in products)

    return render_template('store_owner/product_list.html',
                           store=store,
                           products=products,
                           categories=categories,
                           q=q,
                           selected_category=category_id,
                           total_products_value=total_products_value)

@store_bp.route('/store/<int:store_id>/products/new', methods=['GET', 'POST'])
@role_required('owner')
def new_product(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    if not is_store_active(store):
        flash('هذا المتجر غير نشط، يجب دفع الاشتراك')
        return redirect(url_for('store.store_subscription', store_id=store.id))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        product_code = request.form.get('product_code', '').strip()
        description = request.form.get('description', '').strip()
        price = request.form.get('price', type=float)
        stock_quantity = request.form.get('stock_quantity', type=int, default=0)
        category_id = request.form.get('category_id')
        options = request.form.get('options', '').strip()

        is_offer = request.form.get('is_offer') == 'yes'
        offer_price = request.form.get('offer_price', type=float)
        original_price = request.form.get('original_price', type=float)
        offer_description = request.form.get('offer_description', '').strip()
        hide_price = request.form.get('hide_price') == 'yes'

        if not name or (price is None and not hide_price):
            flash('اسم المنتج والسعر مطلوبان')
            return redirect(url_for('store.new_product', store_id=store.id))

        if hide_price and price is None:
            price = 0.0

        if price < 0 or stock_quantity < 0:
            flash('القيم لا يمكن أن تكون سالبة')
            return redirect(url_for('store.new_product', store_id=store.id))

        category = None
        if category_id:
            category = db.session.get(Category, int(category_id))
            if not category or category.store_id != store.id:
                flash('التصنيف غير صالح')
                return redirect(url_for('store.new_product', store_id=store.id))

        main_image = None
        main_file = request.files.get('main_image')
        if main_file and main_file.filename != '':
            try:
                main_image = save_image(main_file)
            except ValueError as e:
                flash(str(e), 'error')
                return redirect(url_for('store.new_product', store_id=store.id))

        sub_images = []
        uploaded_files = request.files.getlist('sub_images')
        for file in uploaded_files:
            if len(sub_images) >= 4:
                break
            if file and file.filename != '':
                try:
                    saved_name = save_image(file)
                    if saved_name:
                        sub_images.append(saved_name)
                except ValueError as e:
                    flash(str(e), 'error')
                    return redirect(url_for('store.new_product', store_id=store.id))

        video_file = request.files.get('video')
        video_filename = None
        if video_file and video_file.filename != '':
            try:
                video_filename = save_video(video_file)
            except ValueError as e:
                flash(str(e), 'error')
                return redirect(url_for('store.new_product', store_id=store.id))

        final_price = price
        if is_offer:
            if offer_price is not None and offer_price >= 0:
                final_price = offer_price
            else:
                offer_price = price
                final_price = price
        else:
            offer_price = None
            original_price = None
            offer_description = ''

        product = Product(
            store_id=store.id,
            name=name,
            product_code=product_code,
            description=description,
            price=final_price,
            is_offer=is_offer,
            offer_price=offer_price if is_offer else None,
            original_price=original_price if is_offer else None,
            offer_description=offer_description if is_offer else '',
            stock_quantity=stock_quantity,
            category_id=category.id if category else None,
            main_image=main_image,
            sub_images=','.join(sub_images) if sub_images else None,
            video=video_filename,
            options=options,
            hide_price=hide_price
        )
        db.session.add(product)
        db.session.add(product)
        db.session.flush()

        if video_filename:
            reel = Reel(
                store_id=store.id,
                product_id=product.id,
                video_url=video_filename,
                thumbnail_url=main_image if main_image else None,
                caption=name,
                views=0,
                is_active=True
            )
            db.session.add(reel)

        db.session.commit()
        if is_offer:
            try:
                from shared.services.notification_service import NotificationService
                NotificationService.notify_new_offer(product)
            except Exception:
                pass
        flash('تم إضافة المنتج')
        return redirect(url_for('store.store_products', store_id=store.id))

    categories = Category.query.filter_by(store_id=store.id).all()
    return render_template('store_owner/product_form.html', store=store, product=None, categories=categories)

@store_bp.route('/store/<int:store_id>/products/<int:product_id>/edit', methods=['GET', 'POST'])
@role_required('owner')
def edit_product(store_id, product_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    product = Product.query.get_or_404(product_id)
    if product.store_id != store.id:
        abort(403)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        product_code = request.form.get('product_code', '').strip()
        description = request.form.get('description', '').strip()
        price = request.form.get('price', type=float)
        stock_quantity = request.form.get('stock_quantity', type=int, default=0)
        category_id = request.form.get('category_id')
        options = request.form.get('options', '').strip()

        is_offer = request.form.get('is_offer') == 'yes'
        offer_price = request.form.get('offer_price', type=float)
        original_price = request.form.get('original_price', type=float)
        offer_description = request.form.get('offer_description', '').strip()
        hide_price = request.form.get('hide_price') == 'yes'

        if not name or (price is None and not hide_price):
            flash('اسم المنتج والسعر مطلوبان')
            return redirect(url_for('store.edit_product', store_id=store.id, product_id=product.id))

        if hide_price and price is None:
            price = 0.0

        if price < 0 or stock_quantity < 0:
            flash('القيم لا يمكن أن تكون سالبة')
            return redirect(url_for('store.edit_product', store_id=store.id, product_id=product.id))

        category = None
        if category_id:
            category = db.session.get(Category, int(category_id))
            if not category or category.store_id != store.id:
                flash('التصنيف غير صالح')
                return redirect(url_for('store.edit_product', store_id=store.id, product_id=product.id))

        main_file = request.files.get('main_image')
        if main_file and main_file.filename != '':
            old_url = product.main_image
            try:
                new_main = save_image(main_file, old_url=old_url)
                product.main_image = new_main
            except ValueError as e:
                flash(str(e), 'error')
                return redirect(url_for('store.edit_product', store_id=store.id, product_id=product.id))

        if request.form.get('remove_main_image') == 'yes':
            if product.main_image:
                delete_local_file(product.main_image)
                product.main_image = None

        existing_sub = []
        if product.sub_images:
            existing_sub = [img.strip() for img in product.sub_images.split(',') if img.strip()]

        remove_sub_images = request.form.getlist('remove_existing_sub_images')
        for img in remove_sub_images:
            if img in existing_sub:
                existing_sub.remove(img)
                delete_local_file(img)

        uploaded_files = request.files.getlist('sub_images')
        for file in uploaded_files:
            if len(existing_sub) >= 4:
                break
            if file and file.filename != '':
                try:
                    saved_name = save_image(file)
                    if saved_name:
                        existing_sub.append(saved_name)
                except ValueError as e:
                    flash(str(e), 'error')
                    return redirect(url_for('store.edit_product', store_id=store.id, product_id=product.id))

        product.sub_images = ','.join(existing_sub) if existing_sub else None

        new_video_saved = False
        if request.form.get('remove_video') == 'yes':
            if product.video:
                delete_local_file(product.video)
                product.video = None
                existing_reel = Reel.query.filter_by(product_id=product.id).first()
                if existing_reel:
                    db.session.delete(existing_reel)
        else:
            video_file = request.files.get('video')
            if video_file and video_file.filename != '':
                old_url = product.video
                try:
                    new_video = save_video(video_file, old_url=old_url)
                    product.video = new_video
                    new_video_saved = True
                except ValueError as e:
                    flash(str(e), 'error')
                    return redirect(url_for('store.edit_product', store_id=store.id, product_id=product.id))

        product.name = name
        product.product_code = product_code
        product.description = description
        product.stock_quantity = stock_quantity
        product.category_id = category.id if category else None
        product.options = options

        final_price = price
        if is_offer:
            if offer_price is not None and offer_price >= 0:
                final_price = offer_price
            else:
                offer_price = price
                final_price = price
        else:
            offer_price = None
            original_price = None
            offer_description = ''

        product.price = final_price
        product.is_offer = is_offer
        product.offer_price = offer_price if is_offer else None
        product.original_price = original_price if is_offer else None
        product.offer_description = offer_description if is_offer else ''
        product.hide_price = hide_price

        db.session.flush()

        if product.video:
            existing_reel = Reel.query.filter_by(product_id=product.id).first()
            if existing_reel:
                existing_reel.video_url = product.video
                existing_reel.thumbnail_url = product.main_image if product.main_image else None
                existing_reel.caption = product.name
                existing_reel.is_active = True
                if new_video_saved:
                    existing_reel.views = 0
            else:
                reel = Reel(
                    store_id=store.id,
                    product_id=product.id,
                    video_url=product.video,
                    thumbnail_url=product.main_image if product.main_image else None,
                    caption=product.name,
                    views=0,
                    is_active=True
                )
                db.session.add(reel)
        else:
            existing_reel = Reel.query.filter_by(product_id=product.id).first()
            if existing_reel:
                db.session.delete(existing_reel)

        db.session.commit()
        flash('تم حفظ تعديلات المنتج')
        return redirect(url_for('store.store_products', store_id=store.id))

    categories = Category.query.filter_by(store_id=store.id).all()
    return render_template('store_owner/product_form.html', store=store, product=product, categories=categories)

@store_bp.route('/store/<int:store_id>/products/<int:product_id>/delete', methods=['POST'])
@role_required('owner')
def delete_product(store_id, product_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    product = Product.query.get_or_404(product_id)
    if product.store_id != store.id:
        abort(403)

    if product.main_image:
        delete_local_file(product.main_image)
    if product.sub_images:
        for img in product.sub_images.split(','):
            img = img.strip()
            if img:
                delete_local_file(img)
    if product.video:
        delete_local_file(product.video)

    existing_reel = Reel.query.filter_by(product_id=product.id).first()
    if existing_reel:
        db.session.delete(existing_reel)

    db.session.delete(product)
    db.session.commit()
    flash('تم حذف المنتج')
    return redirect(url_for('store.store_products', store_id=store.id))
