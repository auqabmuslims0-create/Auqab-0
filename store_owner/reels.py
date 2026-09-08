from flask import render_template, request, redirect, url_for, flash, abort
from database import db
from models import Reel, Product
from shared.utils import is_store_active, save_video, save_image, delete_local_file
from shared.decorators import role_required
from . import store_bp
from .common import check_store_access

@store_bp.route('/store/<int:store_id>/reels')
@role_required('owner')
def store_reels(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    reels = Reel.query.filter_by(store_id=store.id).order_by(Reel.created_at.desc()).all()
    return render_template('store_owner/reels.html', store=store, reels=reels)

@store_bp.route('/store/<int:store_id>/reels/new', methods=['GET', 'POST'])
@role_required('owner')
def new_reel(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    if not is_store_active(store):
        flash('هذا المتجر غير نشط، يجب دفع الاشتراك')
        return redirect(url_for('store.store_subscription', store_id=store.id))

    if request.method == 'POST':
        product_id = request.form.get('product_id')
        if product_id and product_id.strip():
            product_id = int(product_id)
            product = Product.query.filter_by(id=product_id, store_id=store.id).first()
            if not product:
                flash('المنتج غير صالح')
                return redirect(url_for('store.new_reel', store_id=store.id))
        else:
            product_id = None

        caption = request.form.get('caption', '').strip()

        video_file = request.files.get('video')
        if not video_file or video_file.filename == '':
            flash('يجب اختيار ملف فيديو', 'error')
            return redirect(url_for('store.new_reel', store_id=store.id))

        video_filename = save_video(video_file)
        if not video_filename:
            flash('فشل رفع الفيديو أو الصيغة غير مدعومة', 'error')
            return redirect(url_for('store.new_reel', store_id=store.id))

        thumbnail_filename = None
        thumbnail_file = request.files.get('thumbnail')
        if thumbnail_file and thumbnail_file.filename != '':
            thumbnail_filename = save_image(thumbnail_file)

        reel = Reel(
            store_id=store.id,
            product_id=product_id,
            video_url=video_filename,
            thumbnail_url=thumbnail_filename,
            caption=caption,
            views=0,
            is_active=True
        )
        db.session.add(reel)
        db.session.commit()
        flash('تم إضافة الريل بنجاح')
        return redirect(url_for('store.store_reels', store_id=store.id))

    products = Product.query.filter_by(store_id=store.id).all()
    return render_template('store_owner/reel_form.html', store=store, products=products)

@store_bp.route('/store/<int:store_id>/reels/<int:reel_id>/delete', methods=['POST'])
@role_required('owner')
def delete_reel(store_id, reel_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    reel = Reel.query.get_or_404(reel_id)
    if reel.store_id != store.id:
        abort(403)

    if reel.video_url:
        delete_local_file(reel.video_url)
    if reel.thumbnail_url:
        delete_local_file(reel.thumbnail_url)

    db.session.delete(reel)
    db.session.commit()
    flash('تم حذف الريل')
    return redirect(url_for('store.store_reels', store_id=store.id))
