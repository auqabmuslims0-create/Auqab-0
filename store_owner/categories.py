from flask import render_template, request, redirect, url_for, flash, abort, jsonify
from database import db
from models import Category, Product
from sqlalchemy import func
from shared.decorators import role_required
from . import store_bp
from .common import check_store_access


def _safe_next_url(next_url):
    """يسمح فقط بمسارات داخلية تبدأ بـ / ولا تبدأ بـ //"""
    if not next_url:
        return ''
    next_url = next_url.strip()
    if not next_url.startswith('/') or next_url.startswith('//'):
        return ''
    return next_url


@store_bp.route('/store/<int:store_id>/categories')
@role_required('owner')
def store_categories(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    # S8: عدد المنتجات لكل تصنيف في استعلام واحد (بدل N+1)
    categories = Category.query.filter_by(store_id=store.id).order_by(Category.name).all()

    counts = dict(db.session.query(
        Product.category_id, func.count(Product.id)
    ).filter(
        Product.store_id == store.id,
        Product.category_id.isnot(None)
    ).group_by(Product.category_id).all())

    # إجمالي منتجات المتجر (لزر "إضافة منتجات" الرئيسي)
    total_products = Product.query.filter_by(store_id=store.id).count()

    return render_template('store_owner/category_list.html',
                           store=store,
                           categories=categories,
                           category_counts=counts,
                           total_products=total_products)


@store_bp.route('/store/<int:store_id>/categories/<int:category_id>/products.json')
@role_required('owner')
def category_products_json(store_id, category_id):
    """S8: JSON لمنتجات تصنيف معين (يُستخدم في modal)."""
    result = check_store_access(store_id)
    if result[0] is None:
        return jsonify({'error': 'unauthorized'}), 401
    user, store = result

    category = db.session.get(Category, category_id)
    if not category or category.store_id != store.id:
        return jsonify({'error': 'not found'}), 404

    products = Product.query.filter_by(
        store_id=store.id,
        category_id=category_id
    ).order_by(Product.name).all()

    data = []
    for p in products:
        data.append({
            'id': p.id,
            'name': p.name,
            'main_image': p.main_image or '',
            'price': p.effective_price if hasattr(p, 'effective_price') else p.price,
            'stock_quantity': p.stock_quantity,
            'hide_price': bool(p.hide_price),
        })

    return jsonify({
        'category': {'id': category.id, 'name': category.name},
        'products': data,
    })


@store_bp.route('/store/<int:store_id>/categories/<int:category_id>/manage-products', methods=['GET', 'POST'])
@role_required('owner')
def manage_category_products(store_id, category_id):
    """S8: صفحة اختيار/إزالة منتجات التصنيف."""
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    category = db.session.get(Category, category_id)
    if not category or category.store_id != store.id:
        abort(404)

    if request.method == 'POST':
        selected_ids_raw = request.form.getlist('product_ids')
        try:
            selected_ids = [int(pid) for pid in selected_ids_raw] if selected_ids_raw else []
        except (ValueError, TypeError):
            flash('معرفات غير صالحة', 'error')
            return redirect(url_for('store.manage_category_products',
                                    store_id=store.id, category_id=category.id))

        try:
            # 1) حرّر كل المنتجات الحالية من هذا التصنيف
            Product.query.filter_by(
                store_id=store.id, category_id=category.id
            ).update({'category_id': None}, synchronize_session=False)

            # 2) اربط المنتجات المحددة (فقط التي تنتمي للمتجر)
            if selected_ids:
                Product.query.filter(
                    Product.store_id == store.id,
                    Product.id.in_(selected_ids)
                ).update({'category_id': category.id}, synchronize_session=False)

            db.session.commit()
            flash(f'تم تحديث منتجات التصنيف "{category.name}"', 'success')
        except Exception:
            db.session.rollback()
            flash('حدث خطأ أثناء حفظ التعديلات', 'error')

        return redirect(url_for('store.store_categories', store_id=store.id))

    # GET: كل منتجات المتجر + المحدد منها حالياً
    all_products = Product.query.filter_by(store_id=store.id).order_by(Product.name).all()
    selected_ids = {p.id for p in all_products if p.category_id == category.id}

    return render_template('store_owner/category_products.html',
                           store=store,
                           category=category,
                           all_products=all_products,
                           selected_ids=selected_ids)


@store_bp.route('/store/<int:store_id>/categories/new', methods=['GET', 'POST'])
@role_required('owner')
def new_category(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    next_url = _safe_next_url(request.args.get('next', ''))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        parent_id = request.form.get('parent_id')
        next_url = _safe_next_url(request.form.get('next', '').strip())

        if not name:
            flash('اسم التصنيف مطلوب')
            return redirect(url_for('store.new_category', store_id=store.id, next=next_url))

        parent = None
        if parent_id:
            parent = db.session.get(Category, int(parent_id))
            if not parent or parent.store_id != store.id:
                flash('التصنيف الأب غير صالح')
                return redirect(url_for('store.new_category', store_id=store.id, next=next_url))

        category = Category(name=name, parent_id=parent.id if parent else None, store_id=store.id)
        db.session.add(category)
        db.session.commit()

        if next_url:
            flash(f'تم إنشاء التصنيف "{category.name}" وتحديده تلقائياً', 'success')
            separator = '&' if '?' in next_url else '?'
            return redirect(f'{next_url}{separator}category_id={category.id}')

        flash('تم إنشاء التصنيف', 'success')
        return redirect(url_for('store.store_categories', store_id=store.id))

    parent_categories = Category.query.filter_by(store_id=store.id, parent_id=None).all()
    return render_template('store_owner/category_form.html',
                           store=store, category=None,
                           parent_categories=parent_categories,
                           next_url=next_url)


@store_bp.route('/store/<int:store_id>/categories/<int:category_id>/edit', methods=['GET', 'POST'])
@role_required('owner')
def edit_category(store_id, category_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    category = Category.query.get_or_404(category_id)
    if category.store_id != store.id:
        abort(403)

    next_url = _safe_next_url(request.args.get('next', ''))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        parent_id = request.form.get('parent_id')
        next_url = _safe_next_url(request.form.get('next', '').strip())

        if not name:
            flash('اسم التصنيف مطلوب')
            return redirect(url_for('store.edit_category',
                                    store_id=store.id, category_id=category.id, next=next_url))

        parent = None
        if parent_id:
            parent = db.session.get(Category, int(parent_id))
            if not parent or parent.store_id != store.id:
                flash('التصنيف الأب غير صالح')
                return redirect(url_for('store.edit_category',
                                        store_id=store.id, category_id=category.id, next=next_url))

        category.name = name
        category.parent_id = parent.id if parent else None
        db.session.commit()

        if next_url:
            separator = '&' if '?' in next_url else '?'
            return redirect(f'{next_url}{separator}category_id={category.id}')

        flash('تم حفظ التعديلات')
        return redirect(url_for('store.store_categories', store_id=store.id))

    parent_categories = Category.query.filter_by(store_id=store.id, parent_id=None).all()
    return render_template('store_owner/category_form.html',
                           store=store, category=category,
                           parent_categories=parent_categories,
                           next_url=next_url)


@store_bp.route('/store/<int:store_id>/categories/<int:category_id>/delete', methods=['POST'])
@role_required('owner')
def delete_category(store_id, category_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    category = Category.query.get_or_404(category_id)
    if category.store_id != store.id:
        abort(403)

    if Category.query.filter_by(parent_id=category.id).first():
        flash('لا يمكن حذف هذا التصنيف لوجود تصنيفات فرعية مرتبطة به. احذف التصنيفات الفرعية أولاً.', 'error')
        return redirect(url_for('store.store_categories', store_id=store.id))

    if Product.query.filter_by(category_id=category.id).first():
        flash('لا يمكن حذف التصنيف لوجود منتجات مرتبطة به', 'error')
        return redirect(url_for('store.store_categories', store_id=store.id))

    db.session.delete(category)
    db.session.commit()
    flash('تم حذف التصنيف')
    return redirect(url_for('store.store_categories', store_id=store.id))
