from database import db
from models import Reel, ReelReaction, ReelComment, Store
from sqlalchemy.orm import joinedload

class ReelRepository:
    @staticmethod
    def get_feed_query():
        return Reel.query.join(Store).filter(
            Reel.is_active == True,
            Store.subscription_status == 'active'
        ).options(
            joinedload(Reel.store),
            joinedload(Reel.product),
            joinedload(Reel.reactions),
            joinedload(Reel.comments).joinedload(ReelComment.user)
        ).order_by(Reel.created_at.desc())

    @staticmethod
    def get_feed(page=1, per_page=10):
        return ReelRepository.get_feed_query().paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_by_id(reel_id):
        return Reel.query.options(
            joinedload(Reel.store),
            joinedload(Reel.product),
            joinedload(Reel.reactions),
            joinedload(Reel.comments).joinedload(ReelComment.user)
        ).get(reel_id)

    @staticmethod
    def increment_view(reel):
        reel.views += 1
        db.session.add(reel)

    @staticmethod
    def get_reaction(reel_id, user_id):
        return ReelReaction.query.filter_by(reel_id=reel_id, user_id=user_id).first()

    @staticmethod
    def create_reaction(reel_id, user_id, reaction_type):
        reaction = ReelReaction(reel_id=reel_id, user_id=user_id, reaction_type=reaction_type)
        db.session.add(reaction)
        return reaction

    @staticmethod
    def update_reaction(reaction, new_type):
        reaction.reaction_type = new_type
        db.session.add(reaction)

    @staticmethod
    def delete_reaction(reaction):
        db.session.delete(reaction)

    @staticmethod
    def create_comment(reel_id, user_id, text):
        comment = ReelComment(reel_id=reel_id, user_id=user_id, text=text)
        db.session.add(comment)
        return comment

    @staticmethod
    def get_comment(comment_id):
        return db.session.get(ReelComment, comment_id)

    @staticmethod
    def update_comment(comment, new_text):
        comment.text = new_text
        db.session.add(comment)

    @staticmethod
    def delete_comment(comment):
        db.session.delete(comment)
