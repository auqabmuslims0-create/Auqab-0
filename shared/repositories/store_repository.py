from database import db
from models import Store
from shared.repositories.order_repository import OrderRepository
from shared.repositories.product_repository import ProductRepository


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
        # حذف المتجر نفسه. العلاقات (منتجات، طلبات، تصنيفات، اشتراكات، مدفوعات، مفضلات)
        # تُدار على مستوى قاعدة البيانات (cascade) أو عبر StoreService إذا لزم.
        db.session.delete(store)

    @staticmethod
    def get_store_orders(store_id, page=1, per_page=20, status=None):
        """تفويض إلى OrderRepository (مصدر واحد للحقيقة)."""
        return OrderRepository.get_orders_by_store(
            store_id, page=page, per_page=per_page, status=status
        )

    @staticmethod
    def get_products(store_id, page=1, per_page=20, category_id=None, search=None):
        """تفويض إلى ProductRepository (مصدر واحد للحقيقة)."""
        return ProductRepository.get_by_store(
            store_id, page=page, per_page=per_page,
            category_id=category_id, search=search
        )
