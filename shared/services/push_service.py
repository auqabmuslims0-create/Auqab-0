import json
from flask import current_app
from pywebpush import webpush, WebPushException
from py_vapid import Vapid
from database import db
from models import PushSubscription
from shared.utils import get_setting, set_setting

DEFAULT_VAPID_SUBJECT = "mailto:admin@example.com"

def get_or_create_vapid_keys():
    public_key = get_setting('vapid_public_key')
    private_key = get_setting('vapid_private_key')
    if public_key and private_key:
        return public_key, private_key

    vapid = Vapid()
    vapid.generate_keys()
    public_key = vapid.public_key
    private_key = vapid.private_key

    set_setting('vapid_public_key', public_key)
    set_setting('vapid_private_key', private_key)
    return public_key, private_key

def get_vapid_subject():
    return get_setting('vapid_subject', DEFAULT_VAPID_SUBJECT)

def send_web_push(subscription_info, payload):
    try:
        public_key, private_key = get_or_create_vapid_keys()
        vapid_subject = get_vapid_subject()
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=private_key,
            vapid_claims={"sub": vapid_subject}
        )
        return True
    except WebPushException as e:
        current_app.logger.error(f"WebPushException: {e}")
        if e.response and e.response.status_code in [404, 410]:
            raise e
        return False
    except Exception as e:
        current_app.logger.error(f"Push error: {e}")
        return False

def send_to_user(user_id, notification):
    subs = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subs:
        return 0

    payload = {
        'title': notification.title or 'إشعار جديد',
        'message': notification.message,
        'url': notification.link or '/',
        'icon': '/static/icons/icon-192.png',
        'badge': '/static/icons/icon-96.png'
    }

    count_sent = 0
    invalid_subs = []

    for sub in subs:
        subscription_info = {
            'endpoint': sub.endpoint,
            'keys': {
                'p256dh': sub.p256dh,
                'auth': sub.auth
            }
        }
        try:
            if send_web_push(subscription_info, payload):
                count_sent += 1
        except WebPushException as e:
            if e.response and e.response.status_code in [404, 410]:
                invalid_subs.append(sub)

    if invalid_subs:
        for sub in invalid_subs:
            db.session.delete(sub)
        db.session.commit()

    return count_sent

def send_to_users(user_ids, notification):
    count = 0
    for uid in user_ids:
        count += send_to_user(uid, notification)
    return count

def cleanup_invalid_subscriptions():
    """حذف الاشتراكات غير الصالحة (تُستدعى دورياً)."""
    subs = PushSubscription.query.all()
    invalid_ids = []
    for sub in subs:
        if not sub.endpoint.startswith('http'):
            invalid_ids.append(sub.id)
    if invalid_ids:
        PushSubscription.query.filter(PushSubscription.id.in_(invalid_ids)).delete(synchronize_session=False)
        db.session.commit()
