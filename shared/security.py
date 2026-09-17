from datetime import timedelta
import base64
import hashlib
import secrets
from flask import request, current_app
from cryptography.fernet import Fernet, InvalidToken
from database import db
from models import LoginAttempt, PasswordResetAttempt
from shared.time_utils import current_time


# ═══════════════════════════════════════════════════════════════
# IP العميل — آمن خلف reverse proxy
# ═══════════════════════════════════════════════════════════════
def get_client_ip():
    """
    إرجاع IP العميل بشكل آمن.
    - عند تفعيل TRUST_PROXY_HEADERS=1 (مع ProxyFix في app.py)،
      يصبح request.remote_addr هو IP العميل الحقيقي بعد إعادة الكتابة.
    - عند التعطيل، request.remote_addr هو IP الاتصال المباشر (لا يمكن تزويره).
    - لا نقرأ X-Forwarded-For يدوياً أبداً لأنها قابلة للتزوير من العميل.
    """
    return request.remote_addr or 'unknown'


# ═══════════════════════════════════════════════════════════════
# تشفير قيم الجلسة — لحماية password_hash من تسريب محتمل
# ═══════════════════════════════════════════════════════════════
# Flask sessions موقّعة (signed) لكن غير مشفّرة. أي شخص يقرأ الكوكي
# (XSS أو جهاز مسروق) يمكنه فك base64 ورؤية المحتوى. نُشفّر هنا القيم
# الحساسة قبل وضعها في الجلسة باستخدام Fernet المشتق من SECRET_KEY.
#
# Fernet = AES-128-CBC + HMAC-SHA256 — معيار موثوق من مكتبة cryptography.

def _get_fernet():
    """إنشاء كائن Fernet من مفتاح مشتق من SECRET_KEY (256-bit)."""
    secret = current_app.config.get('SECRET_KEY')
    if not secret:
        raise RuntimeError('SECRET_KEY not configured — cannot encrypt session data')
    # اشتقاق مفتاح Fernet صالح (32 بايت base64-urlsafe) من SECRET_KEY
    key_material = hashlib.sha256(secret.encode('utf-8')).digest()
    fernet_key = base64.urlsafe_b64encode(key_material)
    return Fernet(fernet_key)


def encrypt_session_secret(plaintext):
    """
    تشفير قيمة قبل وضعها في كوكي الجلسة.
    يعيد None إذا كانت القيمة فارغة، وإلا يعيد token Fernet نصي.
    """
    if not plaintext:
        return None
    return _get_fernet().encrypt(plaintext.encode('utf-8')).decode('ascii')


def decrypt_session_secret(token):
    """
    فك تشفير قيمة من الجلسة.

    - إذا كان الرمز Fernet صحيحاً: يفك تشفيره.
    - إذا فشل الفك (جلسات قديمة من قبل هذا التحديث تحتوي plaintext):
      يعيد النص كما هو — backward compatibility.
    - إذا كانت القيمة فارغة: يعيد None.
    """
    if not token:
        return None
    try:
        return _get_fernet().decrypt(token.encode('ascii')).decode('utf-8')
    except (InvalidToken, UnicodeEncodeError, UnicodeDecodeError, ValueError, TypeError):
        # دعم الجلسات القديمة: القيمة قد تكون نصاً غير مشفّر من نشر سابق
        return token


# ═══════════════════════════════════════════════════════════════
# محاولات تسجيل الدخول الفاشلة — rate limiting
# ═══════════════════════════════════════════════════════════════
def record_login_attempt(ip, user_id=None):
    """
    تسجيل محاولة تسجيل دخول فاشلة مع تنظيف المحاولات القديمة.

    - user_id: عند توفره، تُربط المحاولة بالمستخدم (يتيح rate limiting
      على مستوى المستخدم لمنع هجمات IP rotation).
    - user_id=None: تُربط بالـ IP فقط (سلوك الوضع الحالي).
    """
    cutoff = current_time() - timedelta(minutes=15)
    LoginAttempt.query.filter(
        LoginAttempt.ip_address == ip,
        LoginAttempt.attempted_at < cutoff
    ).delete(synchronize_session=False)

    attempt = LoginAttempt(ip_address=ip, user_id=user_id)
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


def get_login_attempts_for_user(user_id, minutes=15):
    """
    عدد محاولات تسجيل الدخول الفاشلة لهذا المستخدم عبر جميع الـ IPs
    خلال الفترة المحددة. يستخدم لمنع هجمات IP rotation.
    """
    cutoff = current_time() - timedelta(minutes=minutes)
    return LoginAttempt.query.filter(
        LoginAttempt.user_id == user_id,
        LoginAttempt.attempted_at >= cutoff
    ).count()


def clear_login_attempts(ip):
    """مسح محاولات تسجيل الدخول الفاشلة لـ IP محدد."""
    LoginAttempt.query.filter_by(ip_address=ip).delete()
    db.session.commit()


# ═══════════════════════════════════════════════════════════════
# محاولات استعادة كلمة المرور
# ═══════════════════════════════════════════════════════════════
def record_reset_attempt(email, ip):
    """تسجيل محاولة استعادة كلمة مرور مع تنظيف المحاولات القديمة لنفس البريد أو IP."""
    cutoff = current_time() - timedelta(minutes=15)
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


# ═══════════════════════════════════════════════════════════════
# أدوات التوكينات الآمنة
# ═══════════════════════════════════════════════════════════════
def generate_secure_token(nbytes=32):
    """
    توليد رمز آمن عشوائي (hex).
    - nbytes=32 (افتراضي): 64 حرف hex = 256 بت — المعيار الحديث للجلسات.
    - nbytes=20: 40 حرف hex = 160 بت — يُستخدم لرموز password reset
      للحفاظ على التوافق مع البيانات الحالية.
    """
    return secrets.token_hex(nbytes)


def hash_token(token):
    """تجزئة رمز باستخدام SHA256 (للتحقق من التوكينات دون تخزينها صريحة)."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()
