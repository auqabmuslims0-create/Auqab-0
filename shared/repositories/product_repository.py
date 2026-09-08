from database import db
from models import Product, Category, Favorite, Review, ProductReaction, ProductComment
from sqlalchemy import func

class ProductRepository:
    @staticmethod
    def get_by_id(product_id):
        return db.session.get(Product, product_id)

    @staticmethod
    def get_by_store(store_id, page=1, per_page=20, category_id=None, search=None, is_offer=None):
        query = Product.query.filter_by(store_id=store_id)
        if category_id:
            query = query.filter(Product.category_id == category_id)
        if search:
            query = query.filter(Product.name.ilike(f'%{search}%'))
        if is_offer is not None:
            query = query.filter(Product.is_offer == is_offer)
        return query.order_by(Product.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def create(product_data):
        product = Product(**product_data)
        db.session.add(product)
        return product

    @staticmethod
    def update(product, **kwargs):
        for key, value in kwargs.items():
            setattr(product, key, value)
        db.session.add(product)

    @staticmethod
    def delete(product):
        db.session.delete(product)

    @staticmethod
    def get_products_by_ids(ids):
        return Product.query.filter(Product.id.in_(ids)).all()

    @staticmethod
    def increment_views(product):
        product.views += 1
        db.session.add(product)

    @staticmethod
    def get_offer_products(page=1, per_page=20):
        return Product.query.filter_by(is_offer=True).order_by(Product.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def search_products(query, page=1, per_page=20):
        search = f'%{query}%'
        return Product.query.filter(
            (Product.name.ilike(search)) |
            (Product.description.ilike(search))
        ).order_by(Product.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
