from database import db
from sqlalchemy import CheckConstraint, Index
from shared.time_utils import current_time

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    product_code = db.Column(db.String(50), nullable=True)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=False)
    is_offer = db.Column(db.Boolean, default=False, index=True)
    offer_price = db.Column(db.Float, nullable=True)
    original_price = db.Column(db.Float, nullable=True)
    offer_description = db.Column(db.Text, nullable=True)
    stock_quantity = db.Column(db.Integer, default=0)
    options = db.Column(db.Text, nullable=True)
    main_image = db.Column(db.String(300), nullable=True)
    sub_images = db.Column(db.Text, nullable=True)
    video = db.Column(db.String(300), nullable=True)
    views = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=current_time, index=True)

    __table_args__ = (
        CheckConstraint('price >= 0', name='ck_product_price_non_negative'),
        CheckConstraint('offer_price IS NULL OR offer_price >= 0', name='ck_product_offer_price_non_negative'),
        CheckConstraint('stock_quantity >= 0', name='ck_product_stock_non_negative'),
        Index('ix_product_store_created', 'store_id', 'created_at'),
        Index('ix_product_offer_created', 'is_offer', 'created_at'),
        Index('ix_product_store_offer', 'store_id', 'is_offer'),
    )

    store = db.relationship('Store', back_populates='products')
    category = db.relationship('Category', back_populates='products')
    order_items = db.relationship('OrderItem', back_populates='product')
    reviews = db.relationship('Review', back_populates='product', cascade="all, delete-orphan")
    favorites = db.relationship('Favorite', back_populates='product', cascade="all, delete-orphan")
    reactions = db.relationship('ProductReaction', back_populates='product', cascade="all, delete-orphan")
    comments = db.relationship('ProductComment', back_populates='product', cascade="all, delete-orphan")
    cart_items = db.relationship('CartItem', back_populates='product', cascade="all, delete-orphan")
    reels = db.relationship('Reel', back_populates='product', cascade="all, delete-orphan")

    @property
    def images(self):
        result = []
        if self.main_image:
            result.append(self.main_image.strip())
        if self.sub_images:
            result.extend([img.strip() for img in self.sub_images.split(',') if img.strip()])
        return ','.join(result) if result else None

    @images.setter
    def images(self, value):
        if not value:
            self.main_image = None
            self.sub_images = None
            return
        parts = [p.strip() for p in value.split(',') if p.strip()]
        if parts:
            self.main_image = parts[0]
            self.sub_images = ','.join(parts[1:]) if len(parts) > 1 else None
        else:
            self.main_image = None
            self.sub_images = None

    def __repr__(self):
        return f'<Product {self.name}>'

class ProductReaction(db.Model):
    __tablename__ = 'product_reactions'
    __table_args__ = (
        db.UniqueConstraint('product_id', 'user_id', name='uq_product_user_reaction'),
        CheckConstraint("reaction_type IN ('like', 'love', 'wow', 'sad', 'angry')", name='ck_reaction_type_valid')
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    reaction_type = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=current_time)

    product = db.relationship('Product', back_populates='reactions')
    user = db.relationship('User')

class ProductComment(db.Model):
    __tablename__ = 'product_comments'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=current_time)

    product = db.relationship('Product', back_populates='comments')
    user = db.relationship('User', back_populates='product_comments')
