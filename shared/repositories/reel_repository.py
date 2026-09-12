from database import db
from models import Reel, ReelReaction, ReelComment, Store
from sqlalchemy.orm import joinedload
from sqlalchemy import func, desc

# خيارات الترتيب المسموح بها
SORT_OPTIONS = ('views', 'newest', 'reactions', 'comments')
DEFAULT_SORT = 'views'


class ReelRepository:
    @staticmethod
    def is_valid_sort(sort_key):
        return sort_key in SORT_OPTIONS

    @staticmethod
    def get_feed_query(sort_key=DEFAULT_SORT):
        """
        بناء استعلام الريلز مع الترتيب المطلوب.
        - views / newest : ترتيب مباشر
        - reactions / comments : عبر subquery مع GROUP BY لتفادي التكرار
        """
        if not ReelRepository.is_valid_sort(sort_key):
            sort_key = DEFAULT_SORT

        query = Reel.query.join(Store).filter(
            Reel.is_active == True,
            Store.subscription_status == 'active'
        )

        if sort_key == 'reactions':
            subq = (
                db.session.query(
                    ReelReaction.reel_id.label('reel_id'),
                    func.count(ReelReaction.id).label('cnt')
                )
                .group_by(ReelReaction.reel_id)
                .subquery()
            )
            query = query.outerjoin(subq, Reel.id == subq.c.reel_id)
            query = query.order_by(
                func.coalesce(subq.c.cnt, 0).desc(),
                Reel.created_at.desc()
            )
        elif sort_key == 'comments':
            subq = (
                db.session.query(
                    ReelComment.reel_id.label('reel_id'),
                    func.count(ReelComment.id).label('cnt')
                )
                .group_by(ReelComment.reel_id)
                .subquery()
            )
            query = query.outerjoin(subq, Reel.id == subq.c.reel_id)
            query = query.order_by(
                func.coalesce(subq.c.cnt, 0).desc(),
                Reel.created_at.desc()
            )
        elif sort_key == 'newest':
            query = query.order_by(Reel.created_at.desc())
        else:  # views (default)
            query = query.order_by(Reel.views.desc(), Reel.created_at.desc())

        query = query.options(
            joinedload(Reel.store),
            joinedload(Reel.product),
            joinedload(Reel.reactions),
            joinedload(Reel.comments).joinedload(ReelComment.user)
        )

        return query

    @staticmethod
    def get_feed(page=1, per_page=10, sort_key=DEFAULT_SORT):
        return ReelRepository.get_feed_query(sort_key).paginate(
            page=page, per_page=per_page, error_out=False
        )

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
        reel.views = (reel.views or 0) + 1
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
