from database import db
from sqlalchemy import Index
from shared.time_utils import current_time

class LoginAttempt(db.Model):
    __tablename__ = 'login_attempts'
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50), nullable=False, index=True)
    attempted_at = db.Column(db.DateTime, default=current_time, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)

    __table_args__ = (
        Index('ix_login_attempt_ip_time', 'ip_address', 'attempted_at'),
    )

    user = db.relationship('User', foreign_keys=[user_id])

class PasswordReset(db.Model):
    __tablename__ = 'password_resets'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)

class PasswordResetAttempt(db.Model):
    __tablename__ = 'password_reset_attempts'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=True, index=True)
    ip_address = db.Column(db.String(50), nullable=False, index=True)
    attempted_at = db.Column(db.DateTime, default=current_time, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)

    __table_args__ = (
        Index('ix_reset_email_time', 'email', 'attempted_at'),
        Index('ix_reset_ip_time', 'ip_address', 'attempted_at'),
    )

    user = db.relationship('User', foreign_keys=[user_id])
