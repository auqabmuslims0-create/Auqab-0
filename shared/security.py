from datetime import timedelta
import secrets
import hashlib
from database import db
from models import LoginAttempt, PasswordResetAttempt
from shared.time_utils import current_time

def record_login_attempt(ip):
    """تسجيل محاولة تسجيل دخول فاشلة."""
    attempt = LoginAttempt(ip_address=ip)
    db.session.add(attempt)
    db.session.commit()

def get_login_attempts(ip, minutes=5):
    """عدد محاولات تسجيل الدخول الفاشلة من نفس الـ IP خلال الدقائق المحددة."""
    cutoff = current_time() - timedelta(minutes=minutes)
    return LoginAttempt.query.filter(
        LoginAttempt.ip_address == ip,
        LoginAttempt.attempted_at >= cutoff
    ).count()

def clear_login_attempts(ip):
    """مسح محاولات تسجيل الدخول الفاشلة لـ IP محدد."""
    LoginAttempt.query.filter_by(ip_address=ip).delete()
    db.session.commit()

def record_reset_attempt(email, ip):
    """تسجيل محاولة استعادة كلمة مرور."""
    attempt = PasswordResetAttempt(email=email, ip_address=ip)
    db.session.add(attempt)
    db.session.commit()

def get_reset_attempts_by_email(email, minutes=15):
    """عدد محاولات استعادة كلمة المرور لنفس البريد خلال الدقائق المحددة."""
    cutoff = current_time() - timedelta(minutes=minutes)
    return PasswordResetAttempt.query.filter(
        PasswordResetAttempt.email == email,
        PasswordResetAttempt.attempted_at >= cutoff
    ).count()

def get_reset_attempts_by_ip(ip, minutes=15):
    """عدد محاولات استعادة كلمة المرور من نفس الـ IP خلال الدقائق المحددة."""
    cutoff = current_time() - timedelta(minutes=minutes)
    return PasswordResetAttempt.query.filter(
        PasswordResetAttempt.ip_address == ip,
        PasswordResetAttempt.attempted_at >= cutoff
    ).count()

def generate_secure_token():
    """توليد رمز آمن (مثل CSRF)."""
    return secrets.token_hex(16)

def hash_token(token):
    """تجزئة رمز باستخدام SHA256."""
    return hashlib.sha256(token.encode()).hexdigest()
