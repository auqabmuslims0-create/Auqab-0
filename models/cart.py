from database import db
from sqlalchemy import UniqueConstraint, CheckConstraint
from shared.time_utils import current_time

class CartItem(db.Model):
    __tablename__ = 'cart_items'
    __table_args__ = (
        UniqueConstraint('user_id', 'product_id', name='uq_user_product_cart'),
        CheckConstraint('quantity > 0', name='ck_cartitem_quantity_positive'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=current_time)

    user = db.relationship('User', back_populates='cart_items')
    product = db.relationship('Product', back_populates='cart_items')
    store = db.relationship('Store', back_populates='cart_items')

    def to_dict(self):
        return {
            'product_id': self.product_id,
            'quantity': self.quantity,
            'store_id': self.store_id
        }
