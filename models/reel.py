from database import db
from sqlalchemy import UniqueConstraint, CheckConstraint, Index
from shared.time_utils import current_time

class Reel(db.Model):
    __tablename__ = 'reels'
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True, index=True)
    video_url = db.Column(db.String(300), nullable=False)
    thumbnail_url = db.Column(db.String(300), nullable=True)
    caption = db.Column(db.Text, nullable=True)
    views = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=current_time, index=True)

    __table_args__ = (
        Index('ix_reel_store_created', 'store_id', 'created_at'),
        Index('ix_reel_active_created', 'is_active', 'created_at'),
    )

    store = db.relationship('Store', back_populates='reels')
    product = db.relationship('Product', back_populates='reels')
    reactions = db.relationship('ReelReaction', back_populates='reel', cascade="all, delete-orphan")
    comments = db.relationship('ReelComment', back_populates='reel', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Reel {self.id}>'

class ReelReaction(db.Model):
    __tablename__ = 'reel_reactions'
    __table_args__ = (
        UniqueConstraint('reel_id', 'user_id', name='uq_reel_user_reaction'),
        CheckConstraint("reaction_type IN ('like', 'love', 'wow', 'sad', 'angry')", name='ck_reel_reaction_type_valid')
    )

    id = db.Column(db.Integer, primary_key=True)
    reel_id = db.Column(db.Integer, db.ForeignKey('reels.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    reaction_type = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=current_time)

    reel = db.relationship('Reel', back_populates='reactions')
    user = db.relationship('User', back_populates='reels_reactions')

class ReelComment(db.Model):
    __tablename__ = 'reel_comments'
    id = db.Column(db.Integer, primary_key=True)
    reel_id = db.Column(db.Integer, db.ForeignKey('reels.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=current_time)

    reel = db.relationship('Reel', back_populates='comments')
    user = db.relationship('User', back_populates='reels_comments')
