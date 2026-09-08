from database import db
from models import Store, Product, Order, OrderItem, Category, Subscription, Payment, Favorite, ProductReaction, ProductComment, Review
from sqlalchemy import func

class StoreRepository:
    @staticmethod
    def get_by_id(store_id):
        return db.session.get(Store, store_id)

    @staticmethod
    def get_by_owner(owner_id):
        return Store.query.filter_by(owner_id=owner_id).all()

    @staticmethod
    def get_active_stores():
        return Store.query.filter_by(subscription_status='active').all()

    @staticmethod
    def update_status(store, new_status):
        store.subscription_status = new_status
        db.session.add(store)

    @staticmethod
    def set_expiry(store, expiry_date):
        store.subscription_expiry = expiry_date
        db.session.add(store)

    @staticmethod
    def delete(store):
        # حذف جميع المنتجات والطلبات والتصنيفات والاشتراكات والمدفوعات والمفضلات
        # ملاحظة: يتم تنفيذ الحذف المتسلسل على مستوى قاعدة البيانات، لكن يمكن حذف يدوي للعلاقات غير المرتبطة بـ cascade
        # سنترك المنطق الكامل للخدمة، هنا فقط حذف المتجر نفسه
        db.session.delete(store)

    @staticmethod
    def get_store_orders(store_id, page=1, per_page=20, status=None):
        query = Order.query.filter_by(store_id=store_id)
        if status:
            query = query.filter(Order.status == status)
        return query.order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_products(store_id, page=1, per_page=20, category_id=None, search=None):
        query = Product.query.filter_by(store_id=store_id)
        if category_id:
            query = query.filter(Product.category_id == category_id)
        if search:
            query = query.filter(Product.name.ilike(f'%{search}%'))
        return query.order_by(Product.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
