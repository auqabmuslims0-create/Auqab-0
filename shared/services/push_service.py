import os
import json
import base64
from flask import current_app
from pywebpush import webpush, WebPushException
from py_vapid import Vapid
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
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
    if isinstance(data, str):
        data = data.encode('ascii')
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64url_decode(data):
    if isinstance(data, bytes):
        data = data.decode('ascii')
    padding = '=' * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _extract_raw_public_key(vapid_obj):
    """استخراج المفتاح العام كـ bytes خام (65 بايت)."""
    raw = vapid_obj.public_key
    if isinstance(raw, bytes):
        return raw
    if isinstance(raw, str):
        return raw.encode('ascii')
    try:
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        return raw.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    except Exception:
        pass
    if hasattr(raw, 'public_bytes_raw'):
        try:
            return raw.public_bytes_raw()
        except Exception:
            pass
    raise TypeError(f'Unsupported public_key type: {type(raw)}')


def _pem_to_scalar_b64(pem_str):
    """يحوّل PEM إلى base64url من الرقم السري (32 بايت) — قصير ليدخل في DB."""
    pem_bytes = pem_str.encode('ascii') if isinstance(pem_str, str) else pem_str
    key = serialization.load_pem_private_key(pem_bytes, password=None)
    scalar_int = key.private_numbers().private_value
    scalar_bytes = scalar_int.to_bytes(32, 'big')
    return _b64url_encode(scalar_bytes)


def _scalar_b64_to_pem(scalar_b64):
    """يعيد بناء PEM من الرقم السري base64url."""
    scalar_bytes = _b64url_decode(scalar_b64)
    if len(scalar_bytes) != 32:
        raise ValueError('invalid scalar length')
    scalar_int = int.from_bytes(scalar_bytes, 'big')
    private_key = ec.derive_private_key(scalar_int, ec.SECP256R1())
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    return pem.decode('ascii')


def _generate_vapid_keys():
    """توليد زوج VAPID: (public_b64_87char, scalar_b64_43char)."""
    vapid = Vapid()
    vapid.generate_keys()
    raw_pub = _extract_raw_public_key(vapid)
    public_key_b64 = _b64url_encode(raw_pub)
    private_pem = vapid.private_pem()
    if isinstance(private_pem, bytes):
        private_pem = private_pem.decode('ascii')
    scalar_b64 = _pem_to_scalar_b64(private_pem)
    return public_key_b64, scalar_b64


def _is_valid_public_key(value):
    if not value or not isinstance(value, str):
        return False
    if value.startswith("b'") or value.startswith('b"') or '\\x' in value:
        return False
    try:
        raw = _b64url_decode(value)
        return len(raw) == 65 and raw[0] == 0x04
    except Exception:
        return False


def _is_valid_private_scalar(value):
    """مفتاح خاص صالح = base64url لـ 32 بايت بالضبط."""
    if not value or not isinstance(value, str):
        return False
    if 'BEGIN' in value or len(value) > 100:
        return False
    try:
        return len(_b64url_decode(value)) == 32
    except Exception:
        return False


def get_or_create_vapid_keys():
    """
    إرجاع (public_key_b64, private_pem) — يحوّل تلقائياً من scalar المخزّن.
    """
    public_key = get_setting('vapid_public_key')
    private_scalar = get_setting('vapid_private_key')

    if _is_valid_public_key(public_key) and _is_valid_private_scalar(private_scalar):
        try:
            return public_key, _scalar_b64_to_pem(private_scalar)
        except Exception:
            pass

    if public_key or private_scalar:
        try:
            current_app.logger.warning(
                'VAPID keys invalid or broken — regenerating.'
            )
        except Exception:
            pass

    public_key, private_scalar = _generate_vapid_keys()
    set_setting('vapid_public_key', public_key)
    set_setting('vapid_private_key', private_scalar)
    return public_key, _scalar_b64_to_pem(private_scalar)


def get_vapid_subject():
    subject = get_setting('vapid_subject') or os.environ.get('VAPID_SUBJECT')
    if subject:
        return subject
    base_url = os.environ.get('APP_BASE_URL') or os.environ.get('BASE_URL')
    if base_url and base_url.startswith('http'):
        return base_url.rstrip('/')
    return DEFAULT_VAPID_SUBJECT


def _do_web_push(subscription_info, payload, private_key_pem, vapid_subject):
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
    _, private_key_pem = get_or_create_vapid_keys()
    vapid_subject = get_vapid_subject()
    return _do_web_push(subscription_info, payload, private_key_pem, vapid_subject)


def send_to_user(user_id, notification):
    if not is_push_enabled():
        return 0

    subs = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subs:
        return 0

    _, private_key_pem = get_or_create_vapid_keys()
    vapid_subject = get_vapid_subject()

    subs_data = [
        {'endpoint': s.endpoint, 'p256dh': s.p256dh, 'auth': s.auth}
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
            'keys': {'p256dh': sub_data['p256dh'], 'auth': sub_data['auth']}
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
    subs = PushSubscription.query.all()
    invalid_ids = []
    for sub in subs:
        if not sub.endpoint.startswith('http'):
            invalid_ids.append(sub.id)
    if invalid_ids:
        PushSubscription.query.filter(PushSubscription.id.in_(invalid_ids)).delete(synchronize_session=False)
        db.session.commit()
