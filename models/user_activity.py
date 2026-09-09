from database import db
from shared.time_utils import current_time

class UserActivity(db.Model):
    __tablename__ = 'user_activity'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    last_seen = db.Column(db.DateTime, default=current_time, index=True)

    user = db.relationship('User', backref=db.backref('activity', uselist=False))

    def __repr__(self):
        return f'<UserActivity {self.user_id}>'
