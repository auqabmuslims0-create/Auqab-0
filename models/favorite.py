from database import db
from sqlalchemy import UniqueConstraint, CheckConstraint
from shared.time_utils import current_time

class Favorite(db.Model):
    __tablename__ = 'favorites'
    __table_args__ = (
        UniqueConstraint('user_id', 'product_id', name='uq_user_product_favorite'),
        UniqueConstraint('user_id', 'store_id', name='uq_user_store_favorite'),
        CheckConstraint(
            '(product_id IS NOT NULL AND store_id IS NULL) OR (product_id IS NULL AND store_id IS NOT NULL)',
            name='ck_favorite_one_target'
        ),
        CheckConstraint(
            'product_id IS NOT NULL OR store_id IS NOT NULL',
            name='ck_favorite_at_least_one'
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True, index=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=current_time)

    user = db.relationship('User', back_populates='favorites')
    product = db.relationship('Product', back_populates='favorites')
    store = db.relationship('Store')
