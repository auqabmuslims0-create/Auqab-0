from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from database import db
from models import User, Notification, PushSubscription
from shared.decorators import login_required
from shared.services.notification_service import NotificationService
from shared.repositories.notification_repository import NotificationRepository
from shared.services.push_service import get_or_create_vapid_keys
import json

notifications_bp = Blueprint('notifications', __name__)


def _serialize_notification(notif):
    """Serialization آمن — لا bare except."""
    extra_data = None
    if notif.extra_data:
        try:
            extra_data = json.loads(notif.extra_data)
        except (ValueError, TypeError):
            extra_data = notif.extra_data
    return {
        'id': notif.id,
        'title': notif.title,
        'message': notif.message,
        'link': notif.link,
        'type': notif.type,
        'priority': notif.priority,
        'icon': notif.icon,
        'is_read': bool(notif.is_read),
        'extra_data': extra_data,
        'entity_type': notif.entity_type,
        'entity_id': notif.entity_id,
        'created_at': notif.created_at.strftime('%Y-%m-%d %H:%M') if notif.created_at else None,
        'created_at_iso': notif.created_at.isoformat() if notif.created_at else None,
        'read_at': notif.read_at.strftime('%Y-%m-%d %H:%M') if notif.read_at else None,
    }


# ========== صفحة المستخدم ==========

@notifications_bp.route('/notifications')
@login_required
def notifications():
    """صفحة الإشعارات — render أوّلي فقط، JS يتحكم بها بعد ذلك."""
    return render_template('notifications/notifications.html')


# ========== API ==========

@notifications_bp.route('/api/notifications')
@login_required
def api_get_notifications():
    """يجلب الإشعارات مع فلترة + pagination."""
    user_id = session.get('user_id')

    filter_type = request.args.get('type') or None
    filter_read = request.args.get('read')

    # توحيد read: 'true'/'false'/'' → True/False/None
    if filter_read in ('true', 'True', '1'):
        filter_read = True
    elif filter_read in ('false', 'False', '0'):
        filter_read = False
    else:
        filter_read = None

    page = max(1, int(request.args.get('page', 1)))
    per_page = min(int(request.args.get('per_page', 20)), 50)
    offset = (page - 1) * per_page

    notifs = NotificationService.get_user_notifications(
        user_id, limit=per_page, offset=offset,
        filter_type=filter_type, filter_read=filter_read
    )
    total = NotificationRepository.count_user_notifications(
        user_id, filter_type=filter_type, filter_read=filter_read
    )
    total_pages = max(1, (total + per_page - 1) // per_page)

    unread_count = NotificationService.get_unread_count(user_id)

    return jsonify({
        'notifications': [_serialize_notification(n) for n in notifs],
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1,
        },
        'unread_count': unread_count,
    })


@notifications_bp.route('/api/notifications/counts')
@login_required
def api_notification_counts():
    """يُرجع عدد الإشعارات لكل تصنيف (لشارات الفلترة)."""
    user_id = session.get('user_id')

    def _count(**kwargs):
        return NotificationRepository.count_user_notifications(user_id, **kwargs)

    return jsonify({
        'total': _count(),
        'unread': _count(filter_read=False),
        'by_type': {
            'order': _count(filter_type='order'),
            'subscription': _count(filter_type='subscription'),
            'delivery': _count(filter_type='delivery'),
            'message': _count(filter_type='message'),
            'alert': _count(filter_type='alert'),
        },
    })


@notifications_bp.route('/api/notifications/unread-count')
@login_required
def api_unread_count():
    user_id = session.get('user_id')
    return jsonify({'unread_count': NotificationService.get_unread_count(user_id)})


@notifications_bp.route('/api/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def api_mark_read(notif_id):
    user_id = session.get('user_id')
    if NotificationService.mark_as_read(notif_id, user_id):
        return jsonify({
            'message': 'تم التحديد كمقروء',
            'unread_count': NotificationService.get_unread_count(user_id)
        }), 200
    return jsonify({'message': 'فشل التحديث'}), 400


@notifications_bp.route('/api/notifications/read-all', methods=['POST'])
@login_required
def api_mark_all_read():
    user_id = session.get('user_id')
    NotificationService.mark_all_as_read(user_id)
    return jsonify({'message': 'تم تحديد الكل كمقروء', 'unread_count': 0}), 200


@notifications_bp.route('/api/notifications/<int:notif_id>', methods=['DELETE'])
@login_required
def api_delete_notification(notif_id):
    user_id = session.get('user_id')
    if NotificationService.delete(notif_id, user_id):
        return jsonify({
            'message': 'تم الحذف',
            'unread_count': NotificationService.get_unread_count(user_id)
        }), 200
    return jsonify({'message': 'فشل الحذف'}), 400


@notifications_bp.route('/api/notifications/read', methods=['DELETE'])
@login_required
def api_delete_read():
    user_id = session.get('user_id')
    NotificationService.delete_all_read(user_id)
    return jsonify({
        'message': 'تم حذف المقروءة',
        'unread_count': NotificationService.get_unread_count(user_id)
    }), 200


@notifications_bp.route('/api/notifications/delete-selected', methods=['POST'])
@login_required
def api_delete_selected():
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'message': 'لا توجد معرفات'}), 400
    try:
        ids = [int(i) for i in ids]
    except (ValueError, TypeError):
        return jsonify({'message': 'معرفات غير صالحة'}), 400

    try:
        NotificationRepository.delete_selected(user_id, ids)
        db.session.commit()
        return jsonify({
            'message': 'تم حذف المحدد',
            'unread_count': NotificationService.get_unread_count(user_id)
        }), 200
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'خطأ في الحذف'}), 500


# ========== Push Subscription ==========

@notifications_bp.route('/api/notifications/push/vapid_public_key', methods=['GET'])
def push_vapid_public_key():
    public_key, _ = get_or_create_vapid_keys()
    return jsonify({'public_key': public_key})


@notifications_bp.route('/api/notifications/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    data = request.get_json(silent=True) or {}
    subscription = data.get('subscription')
    if not subscription:
        return jsonify({'message': 'بيانات الاشتراك مطلوبة'}), 400

    endpoint = subscription.get('endpoint')
    keys = subscription.get('keys', {})
    p256dh = keys.get('p256dh')
    auth = keys.get('auth')

    if not endpoint or not p256dh or not auth:
        return jsonify({'message': 'بيانات الاشتراك غير مكتملة'}), 400

    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'message': 'يجب تسجيل الدخول'}), 401

    existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if existing:
        # حماية: لا نسمح بالاستيلاء على endpoint مستخدم آخر
        if existing.user_id != user_id:
            return jsonify({'message': 'الاشتراك مرتبط بحساب آخر'}), 409
        # نفس المستخدم — تحديث المفاتيح
        existing.p256dh = p256dh
        existing.auth = auth
        try:
            db.session.commit()
            return jsonify({'message': 'تم تحديث الاشتراك'}), 200
        except Exception:
            db.session.rollback()
            return jsonify({'message': 'حدث خطأ أثناء التحديث'}), 500

    new_sub = PushSubscription(
        user_id=user_id,
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth
    )
    db.session.add(new_sub)
    try:
        db.session.commit()
        return jsonify({'message': 'تم الاشتراك في الإشعارات'}), 201
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'حدث خطأ أثناء الحفظ'}), 500


@notifications_bp.route('/api/notifications/push/unsubscribe', methods=['POST'])
@login_required
def push_unsubscribe():
    data = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint')
    if not endpoint:
        return jsonify({'message': 'endpoint مطلوب'}), 400

    user_id = session.get('user_id')
    sub = PushSubscription.query.filter_by(endpoint=endpoint, user_id=user_id).first()
    if sub:
        db.session.delete(sub)
        try:
            db.session.commit()
            return jsonify({'message': 'تم إلغاء الاشتراك'}), 200
        except Exception:
            db.session.rollback()
            return jsonify({'message': 'حدث خطأ أثناء الإلغاء'}), 500
    return jsonify({'message': 'لا يوجد اشتراك مطابق'}), 404
