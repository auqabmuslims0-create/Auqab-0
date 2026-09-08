from flask import render_template, request, redirect, url_for, flash, abort
from database import db
from models import Category, Product
from shared.decorators import role_required
from . import store_bp
from .common import check_store_access

@store_bp.route('/store/<int:store_id>/categories')
@role_required('owner')
def store_categories(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result
    categories = Category.query.filter_by(store_id=store.id).all()
    return render_template('store_owner/category_list.html', store=store, categories=categories)

@store_bp.route('/store/<int:store_id>/categories/new', methods=['GET', 'POST'])
@role_required('owner')
def new_category(store_id):
    result = check_store_access(store_id)
    if result[0] is None:
        return result[1]
    user, store = result

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        parent_id = request.form.get('parent_id')

        if not name:
            flash('اسم التصنيف مطلوب')
            return redirect(url_for('store.new_category', store_id=store.id))

        parent = None
        if parent_id:
            parent = db.session.get(Category, int(parent_id))
            if not parent or parent.store_id != store.id:
                flash('التصنيف الأب غير صالح')
                return redirect(url_for('store.new_category', store_id=store.id))

        category = Category(name=name, parent_id=parent.id if parent else None, store_id=store.id)
        db.session.add(category)
        db.session.commit()
        flash('تم إنشاء التصنيف')
        return redirect(url_for('store.store_categories', store_id=store.id))

    parent_categories = Category.query.filter_by(store_id=store.id, parent_id=None).all()
    return render_template('store_owner/category_form.html', store=store, category=None, parent_categories=parent_categories)

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

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        parent_id = request.form.get('parent_id')

        if not name:
            flash('اسم التصنيف مطلوب')
            return redirect(url_for('store.edit_category', store_id=store.id, category_id=category.id))

        parent = None
        if parent_id:
            parent = db.session.get(Category, int(parent_id))
            if not parent or parent.store_id != store.id:
                flash('التصنيف الأب غير صالح')
                return redirect(url_for('store.edit_category', store_id=store.id, category_id=category.id))

        category.name = name
        category.parent_id = parent.id if parent else None
        db.session.commit()
        flash('تم حفظ التعديلات')
        return redirect(url_for('store.store_categories', store_id=store.id))

    parent_categories = Category.query.filter_by(store_id=store.id, parent_id=None).all()
    return render_template('store_owner/category_form.html', store=store, category=category, parent_categories=parent_categories)

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
        flash('لا يمكن حذف التصنيف لوجود منتجات مرتبطة به')
        return redirect(url_for('store.store_categories', store_id=store.id))

    db.session.delete(category)
    db.session.commit()
    flash('تم حذف التصنيف')
    return redirect(url_for('store.store_categories', store_id=store.id))
