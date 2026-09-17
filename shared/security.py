from datetime import timedelta
import secrets
import hashlib
from flask import request
from database import db
from models import LoginAttempt, PasswordResetAttempt
from shared.time_utils import current_time


def get_client_ip():
    """
    إرجاع IP العميل بشكل آمن.

    - عند تفعيل TRUST_PROXY_HEADERS=1 (مع ProxyFix في app.py)،
      يصبح request.remote_addr هو IP العميل الحقيقي بعد إعادة الكتابة.
    - عند التعطيل، request.remote_addr هو IP الاتصال المباشر (لا يمكن تزويره).
    - لا نقرأ X-Forwarded-For يدوياً أبداً لأنها قابلة للتزوير من العميل.
    """
    return request.remote_addr or 'unknown'


def record_login_attempt(ip):
    """تسجيل محاولة تسجيل دخول فاشلة مع تنظيف المحاولات القديمة لنفس الـ IP."""
    cutoff = current_time() - timedelta(minutes=15)
    LoginAttempt.query.filter(
        LoginAttempt.ip_address == ip,
        LoginAttempt.attempted_at < cutoff
    ).delete(synchronize_session=False)

    attempt = LoginAttempt(ip_address=ip)
    db.session.add(attempt)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


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
    """تسجيل محاولة استعادة كلمة مرور مع تنظيف المحاولات القديمة لنفس البريد أو IP."""
    cutoff = current_time() - timedelta(minutes=15)
    # تنظيف المحاولات القديمة لنفس البريد أو نفس الـ IP فقط (وليس الجميع)
    PasswordResetAttempt.query.filter(
        PasswordResetAttempt.attempted_at < cutoff,
        db.or_(
            PasswordResetAttempt.email == email,
            PasswordResetAttempt.ip_address == ip
        )
    ).delete(synchronize_session=False)

    attempt = PasswordResetAttempt(email=email, ip_address=ip)
    db.session.add(attempt)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


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
