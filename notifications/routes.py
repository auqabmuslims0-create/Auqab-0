from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from database import db
from models import User, Notification, PushSubscription
from shared.decorators import login_required
from shared.services.notification_service import NotificationService
from shared.repositories.notification_repository import NotificationRepository
from shared.services.push_service import get_or_create_vapid_keys
import json

notifications_bp = Blueprint('notifications', __name__)

# ========== واجهات المستخدم ==========

@notifications_bp.route('/notifications')
@login_required
def notifications():
    user_id = session.get('user_id')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    notifs = NotificationService.get_user_notifications(user_id, limit=per_page, offset=offset)
    total_count = NotificationRepository.count_user_notifications(user_id)
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    return render_template('notifications/notifications.html',
                           notifs=notifs, page=page, total_pages=total_pages)

@notifications_bp.route('/notifications/mark_read/<int:notif_id>', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    user_id = session.get('user_id')
    if NotificationService.mark_as_read(notif_id, user_id):
        flash('تم تحديد الإشعار كمقروء', 'success')
    else:
        flash('تعذر تحديث الإشعار', 'error')
    return redirect(url_for('notifications.notifications'))

@notifications_bp.route('/notifications/mark_all_read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    user_id = session.get('user_id')
    NotificationService.mark_all_as_read(user_id)
    flash('تم تحديد جميع الإشعارات كمقروءة', 'success')
    return redirect(url_for('notifications.notifications'))

@notifications_bp.route('/notifications/delete/<int:notif_id>', methods=['POST'])
@login_required
def delete_notification(notif_id):
    user_id = session.get('user_id')
    if NotificationService.delete(notif_id, user_id):
        flash('تم حذف الإشعار', 'success')
    else:
        flash('تعذر حذف الإشعار', 'error')
    return redirect(url_for('notifications.notifications'))

@notifications_bp.route('/notifications/delete_read', methods=['POST'])
@login_required
def delete_all_read_notifications():
    user_id = session.get('user_id')
    NotificationService.delete_all_read(user_id)
    flash('تم حذف الإشعارات المقروءة', 'success')
    return redirect(url_for('notifications.notifications'))

@notifications_bp.route('/notifications/delete_selected', methods=['POST'])
@login_required
def delete_selected_notifications():
    user_id = session.get('user_id')
    ids = request.form.getlist('notification_ids')
    if ids:
        try:
            ids = [int(i) for i in ids]
            NotificationRepository.delete_selected(user_id, ids)
            db.session.commit()
            flash('تم حذف الإشعارات المحددة', 'success')
        except Exception as e:
            db.session.rollback()
            flash('حدث خطأ أثناء الحذف', 'error')
    return redirect(url_for('notifications.notifications'))

# ========== API ==========

def serialize_notification(notif):
    extra_data = None
    if notif.extra_data:
        try:
            extra_data = json.loads(notif.extra_data)
        except:
            extra_data = notif.extra_data
    return {
        'id': notif.id,
        'title': notif.title,
        'message': notif.message,
        'link': notif.link,
        'type': notif.type,
        'priority': notif.priority,
        'icon': notif.icon,
        'is_read': notif.is_read,
        'extra_data': extra_data,
        'entity_type': notif.entity_type,
        'entity_id': notif.entity_id,
        'created_at': notif.created_at.strftime('%Y-%m-%d %H:%M') if notif.created_at else None,
        'read_at': notif.read_at.strftime('%Y-%m-%d %H:%M') if notif.read_at else None,
        'expires_at': notif.expires_at.strftime('%Y-%m-%d %H:%M') if notif.expires_at else None
    }

@notifications_bp.route('/api/notifications')
@login_required
def api_get_notifications():
    user_id = session.get('user_id')
    filter_type = request.args.get('type')
    filter_read = request.args.get('read')
    limit = min(int(request.args.get('limit', 20)), 100)
    offset = int(request.args.get('offset', 0))
    notifs = NotificationService.get_user_notifications(
        user_id, limit=limit, offset=offset,
        filter_type=filter_type, filter_read=filter_read
    )
    total_unread = NotificationService.get_unread_count(user_id)
    return jsonify({
        'notifications': [serialize_notification(n) for n in notifs],
        'total_unread': total_unread,
        'limit': limit,
        'offset': offset
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
        return jsonify({'message': 'تم التحديد كمقروء'}), 200
    return jsonify({'message': 'فشل التحديث'}), 400

@notifications_bp.route('/api/notifications/read-all', methods=['POST'])
@login_required
def api_mark_all_read():
    user_id = session.get('user_id')
    NotificationService.mark_all_as_read(user_id)
    return jsonify({'message': 'تم تحديد الكل كمقروء'}), 200

@notifications_bp.route('/api/notifications/<int:notif_id>', methods=['DELETE'])
@login_required
def api_delete_notification(notif_id):
    user_id = session.get('user_id')
    if NotificationService.delete(notif_id, user_id):
        return jsonify({'message': 'تم الحذف'}), 200
    return jsonify({'message': 'فشل الحذف'}), 400

@notifications_bp.route('/api/notifications/read', methods=['DELETE'])
@login_required
def api_delete_read():
    user_id = session.get('user_id')
    NotificationService.delete_all_read(user_id)
    return jsonify({'message': 'تم حذف المقروءة'}), 200

@notifications_bp.route('/api/notifications/delete-selected', methods=['POST'])
@login_required
def api_delete_selected():
    user_id = session.get('user_id')
    data = request.get_json() or {}
    ids = data.get('ids', [])
    if ids:
        try:
            NotificationRepository.delete_selected(user_id, ids)
            db.session.commit()
            return jsonify({'message': 'تم حذف المحدد'}), 200
        except Exception:
            db.session.rollback()
            return jsonify({'message': 'خطأ'}), 500
    return jsonify({'message': 'لا توجد معرفات'}), 400

# ========== Push Subscription APIs ==========

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
        if existing.user_id != user_id:
            existing.user_id = user_id
            existing.p256dh = p256dh
            existing.auth = auth
            try:
                db.session.commit()
                return jsonify({'message': 'تم تحديث الاشتراك'}), 200
            except Exception:
                db.session.rollback()
                return jsonify({'message': 'حدث خطأ أثناء التحديث'}), 500
        return jsonify({'message': 'الاشتراك موجود بالفعل'}), 200

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
