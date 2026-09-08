from database import db
from models import User
from sqlalchemy import func

class UserRepository:
    @staticmethod
    def get_by_id(user_id):
        return db.session.get(User, user_id)

    @staticmethod
    def get_by_username(username):
        return User.query.filter_by(username=username).first()

    @staticmethod
    def get_by_email(email):
        return User.query.filter_by(email=email).first()

    @staticmethod
    def get_active_admins_count(exclude_user_id=None):
        query = User.query.filter_by(role='admin', is_active=True)
        if exclude_user_id:
            query = query.filter(User.id != exclude_user_id)
        return query.count()

    @staticmethod
    def toggle_active(user):
        user.is_active = not user.is_active
        db.session.add(user)

    @staticmethod
    def delete(user):
        db.session.delete(user)

    @staticmethod
    def get_all_users(page=1, per_page=20, role=None, search=None):
        query = User.query
        if role:
            query = query.filter(User.role == role)
        if search:
            query = query.filter(
                (User.username.ilike(f'%{search}%')) |
                (User.email.ilike(f'%{search}%')) |
                (User.phone.ilike(f'%{search}%'))
            )
        return query.order_by(User.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_delivery_persons():
        return User.query.filter_by(role='delivery').all()

    @staticmethod
    def get_available_delivery_persons():
        # يمكن إضافة منطق التوفر لاحقاً
        return User.query.filter_by(role='delivery', is_active=True, is_available=True).all()
