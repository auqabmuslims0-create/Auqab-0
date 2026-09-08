from sqlalchemy.orm import joinedload
from database import db
from models import Reel, ReelReaction, ReelComment, Store
from shared.repositories.reel_repository import ReelRepository
from shared.time_utils import current_time

class ReelService:
    @staticmethod
    def get_feed(page=1, per_page=10, user_id=None):
        pagination = ReelRepository.get_feed(page=page, per_page=per_page)
        reels = pagination.items

        user_reaction_map = {}
        if user_id:
            user_reactions = ReelReaction.query.filter_by(user_id=user_id).all()
            for r in user_reactions:
                user_reaction_map[r.reel_id] = r.reaction_type

        return reels, pagination, user_reaction_map

    @staticmethod
    def get_reel_by_id(reel_id):
        return ReelRepository.get_by_id(reel_id)

    @staticmethod
    def increment_view(reel_id):
        reel = ReelRepository.get_by_id(reel_id)
        if reel:
            ReelRepository.increment_view(reel)
            db.session.commit()

    @staticmethod
    def toggle_reaction(reel_id, user_id, reaction_type):
        reel = ReelRepository.get_by_id(reel_id)
        if not reel:
            raise ValueError('الريل غير موجود')
        existing = ReelRepository.get_reaction(reel_id, user_id)
        if existing:
            if existing.reaction_type == reaction_type:
                ReelRepository.delete_reaction(existing)
                db.session.commit()
                return {'removed': True}
            else:
                ReelRepository.update_reaction(existing, reaction_type)
                db.session.commit()
                return {'updated': True}
        else:
            ReelRepository.create_reaction(reel_id, user_id, reaction_type)
            db.session.commit()
            return {'added': True}

    @staticmethod
    def add_comment(reel_id, user_id, text):
        comment = ReelRepository.create_comment(reel_id, user_id, text)
        db.session.commit()
        return comment

    @staticmethod
    def update_comment(comment_id, user_id, new_text):
        comment = ReelRepository.get_comment(comment_id)
        if not comment:
            return None
        if comment.user_id != user_id:
            return None
        ReelRepository.update_comment(comment, new_text)
        db.session.commit()
        return comment

    @staticmethod
    def delete_comment(comment_id, user_id):
        comment = ReelRepository.get_comment(comment_id)
        if not comment:
            return False
        if comment.user_id != user_id:
            return False
        ReelRepository.delete_comment(comment)
        db.session.commit()
        return True

    @staticmethod
    def serialize_reel(reel, user_reaction_map=None):
        data = {
            'id': reel.id,
            'video_url': reel.video_url,
            'thumbnail_url': reel.thumbnail_url,
            'caption': reel.caption,
            'views': reel.views,
            'created_at': reel.created_at.strftime('%Y-%m-%d %H:%M') if reel.created_at else None,
            'store': {
                'id': reel.store.id,
                'name': reel.store.name,
                'logo_url': reel.store.logo_url,
            },
            'product': None
        }
        if reel.product:
            data['product'] = {
                'id': reel.product.id,
                'name': reel.product.name,
                'price': reel.product.price,
                'is_offer': reel.product.is_offer,
                'original_price': reel.product.original_price,
                'stock_quantity': reel.product.stock_quantity,
            }
        return data
