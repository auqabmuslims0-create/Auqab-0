from database import db
from sqlalchemy import UniqueConstraint, CheckConstraint
from shared.time_utils import current_time

class Review(db.Model):
    __tablename__ = 'reviews'
    __table_args__ = (
        UniqueConstraint('user_id', 'product_id', name='uq_user_product_review'),
        CheckConstraint('rating >= 1 AND rating <= 5', name='ck_review_rating_range')
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=current_time)

    user = db.relationship('User', back_populates='reviews')
    product = db.relationship('Product', back_populates='reviews')
