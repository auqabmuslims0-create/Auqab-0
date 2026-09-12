import os
import json
import base64
from flask import current_app
from pywebpush import webpush, WebPushException
from py_vapid import Vapid
from database import db
from models import PushSubscription
from shared.utils import get_setting, set_setting


DEFAULT_VAPID_SUBJECT = "mailto:admin@example.com"


def is_push_enabled():
    """Push مُفعّل افتراضياً في الإنتاج، ومعطّل في التطوير لتفادي تعليق SQLite."""
    env_value = os.environ.get('PUSH_ENABLED')
    if env_value is not None:
        return env_value.strip() == '1'
    return os.environ.get('FLASK_DEBUG', 'False').lower() != 'true'


def _b64url_encode(data):
    """تحويل bytes إلى base64url بدون padding."""
    if isinstance(data, str):
        data = data.encode('ascii')
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64url_decode(data):
    """تحويل base64url إلى bytes مع إضافة padding تلقائياً."""
    if isinstance(data, bytes):
        data = data.decode('ascii')
    padding = '=' * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _extract_raw_public_key(vapid_obj):
    """
    استخراج المفتاح العام كـ bytes خام (65 بايت uncompressed EC point).
    يتعامل مع اختلافات py_vapid: bytes / str / ECPublicKey object.
    """
    raw = vapid_obj.public_key

    if isinstance(raw, bytes):
        return raw
    if isinstance(raw, str):
        return raw.encode('ascii')

    # كائن cryptography ECPublicKey (py_vapid الحديثة)
    try:
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        return raw.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    except Exception:
        pass

    # بعض الإصدارات توفر طريقة مباشرة
    if hasattr(raw, 'public_bytes_raw'):
        try:
            return raw.public_bytes_raw()
        except Exception:
            pass

    raise TypeError(f'Unsupported public_key type: {type(raw)}')


def _extract_private_pem(vapid_obj):
    """استخراج المفتاح الخاص كـ PEM (str)."""
    try:
        pem = vapid_obj.private_pem()
    except AttributeError:
        # بعض الإصدارات القديمة تستخدم private_key مباشرة
        pem = vapid_obj.private_key
    if isinstance(pem, bytes):
        return pem.decode('ascii')
    return pem


def _is_valid_public_key(value):
    """مفتاح عام صالح = base64url لـ 65 بايت تبدأ بـ 0x04 (uncompressed EC point)."""
    if not value or not isinstance(value, str):
        return False
    if value.startswith("b'") or value.startswith('b"') or '\\x' in value:
        return False
    try:
        raw = _b64url_decode(value)
        return len(raw) == 65 and raw[0] == 0x04
    except Exception:
        return False


def _is_valid_private_pem(value):
    """مفتاح خاص PEM صالح."""
    if not value or not isinstance(value, str):
        return False
    if value.startswith("b'") or value.startswith('b"'):
        return False
    return 'BEGIN PRIVATE KEY' in value or 'BEGIN EC PRIVATE KEY' in value


def _generate_vapid_keys():
    """توليد زوج VAPID جديد بالتنسيقات الصحيحة (base64url + PEM)."""
    vapid = Vapid()
    vapid.generate_keys()
    raw_pub = _extract_raw_public_key(vapid)
    public_key_b64 = _b64url_encode(raw_pub)
    private_pem = _extract_private_pem(vapid)
    return public_key_b64, private_pem


def get_or_create_vapid_keys():
    """
    جلب أو توليد مفاتيح VAPID.
    يكتشف المفاتيح المكسورة (bytes repr القديمة) ويولّد بدائل صحيحة.
    """
    public_key = get_setting('vapid_public_key')
    private_key = get_setting('vapid_private_key')

    if _is_valid_public_key(public_key) and _is_valid_private_pem(private_key):
        return public_key, private_key

    if public_key or private_key:
        try:
            current_app.logger.warning(
                'VAPID keys invalid or broken — regenerating. '
                'Existing push subscriptions will need to be re-created by clients.'
            )
        except Exception:
            pass

    public_key, private_key = _generate_vapid_keys()
    set_setting('vapid_public_key', public_key)
    set_setting('vapid_private_key', private_key)
    return public_key, private_key


def get_vapid_subject():
    """موضوع VAPID (يجب أن يكون mailto: أو https://)."""
    subject = get_setting('vapid_subject') or os.environ.get('VAPID_SUBJECT')
    if subject:
        return subject
    base_url = os.environ.get('APP_BASE_URL') or os.environ.get('BASE_URL')
    if base_url and base_url.startswith('http'):
        return base_url.rstrip('/')
    return DEFAULT_VAPID_SUBJECT


def _do_web_push(subscription_info, payload, private_key_pem, vapid_subject):
    """تنفيذ إرسال push فعلي (بعد جلب البيانات خارج الجلسة)."""
    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=private_key_pem,
            vapid_claims={"sub": vapid_subject},
            timeout=10
        )
        return True
    except WebPushException as e:
        current_app.logger.error(f"WebPushException: {e}")
        if e.response and e.response.status_code in [404, 410]:
            raise
        return False
    except Exception as e:
        current_app.logger.error(f"Push error: {e}")
        return False


def send_web_push(subscription_info, payload):
    """واجهة عامة — تجلب المفاتيح بنفسها."""
    _, private_key_pem = get_or_create_vapid_keys()
    vapid_subject = get_vapid_subject()
    return _do_web_push(subscription_info, payload, private_key_pem, vapid_subject)


def send_to_user(user_id, notification):
    """
    قراءة الاشتراكات + المفاتيح، ثم إغلاق الجلسة قبل الاتصال بالشبكة
    لتفادي احتجاز SQLite lock أثناء انتظار الشبكة.
    """
    if not is_push_enabled():
        return 0

    subs = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subs:
        return 0

    _, private_key_pem = get_or_create_vapid_keys()
    vapid_subject = get_vapid_subject()

    subs_data = [
        {
            'endpoint': s.endpoint,
            'p256dh': s.p256dh,
            'auth': s.auth
        }
        for s in subs
    ]

    db.session.remove()

    payload = {
        'title': notification.title or 'إشعار جديد',
        'message': notification.message,
        'url': notification.link or '/',
        'icon': '/static/icons/icon-192.png',
        'badge': '/static/icons/icon-96.png'
    }

    count_sent = 0
    invalid_endpoints = []

    for sub_data in subs_data:
        subscription_info = {
            'endpoint': sub_data['endpoint'],
            'keys': {
                'p256dh': sub_data['p256dh'],
                'auth': sub_data['auth']
            }
        }
        try:
            if _do_web_push(subscription_info, payload, private_key_pem, vapid_subject):
                count_sent += 1
        except WebPushException as e:
            if e.response and e.response.status_code in [404, 410]:
                invalid_endpoints.append(sub_data['endpoint'])

    if invalid_endpoints:
        try:
            PushSubscription.query.filter(
                PushSubscription.endpoint.in_(invalid_endpoints)
            ).delete(synchronize_session=False)
            db.session.commit()
        except Exception:
            db.session.rollback()
        finally:
            db.session.remove()

    return count_sent


def send_to_users(user_ids, notification):
    if not is_push_enabled():
        return 0
    count = 0
    for uid in user_ids:
        count += send_to_user(uid, notification)
    return count


def cleanup_invalid_subscriptions():
    """حذف الاشتراكات غير الصالحة (endpoints غير http)."""
    subs = PushSubscription.query.all()
    invalid_ids = []
    for sub in subs:
        if not sub.endpoint.startswith('http'):
            invalid_ids.append(sub.id)
    if invalid_ids:
        PushSubscription.query.filter(PushSubscription.id.in_(invalid_ids)).delete(synchronize_session=False)
        db.session.commit()
