from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort, jsonify, current_app
from database import db
from models import User, Order, OrderItem, Store, Notification
from sqlalchemy.orm import joinedload
from shared.time_utils import current_time
from datetime import timedelta
from shared.services.order_service import OrderService
from shared.services.notification_service import NotificationService
from shared.repositories.delivery_repository import DeliveryRepository
from shared.repositories.notification_repository import NotificationRepository
from shared.decorators import role_required, login_required, api_login_required
from blueprints.api.helpers import token_required
from .api.helpers import serialize_order

delivery_bp = Blueprint('delivery', __name__)

# ========== واجهات المستخدم ==========

@delivery_bp.route('/delivery')
@role_required('delivery')
def delivery_dashboard():
    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    status_filter = request.args.get('status', '').strip()
    allowed_statuses = ['ready', 'delivering', 'delivered']

    try:
        query = Order.query.filter_by(delivery_person_id=user.id).options(
            joinedload(Order.store),
            joinedload(Order.customer),
            joinedload(Order.items).joinedload(OrderItem.product)
        )

        if status_filter in allowed_statuses:
            query = query.filter(Order.status == status_filter)

        all_orders = query.order_by(Order.created_at.desc()).limit(50).all()

        ready_orders = [o for o in all_orders if o.status == 'ready']
        delivering_orders = [o for o in all_orders if o.status == 'delivering']
        delivered_orders = [o for o in all_orders if o.status == 'delivered']

        now = current_time()
        map_orders = []
        for order in all_orders:
            if order.latitude and order.longitude:
                if order.status == 'delivered':
                    delivered_time = order.delivered_at or order.created_at
                    if now - delivered_time > timedelta(hours=12):
                        continue
                map_orders.append(order)

        active_orders_count = Order.query.filter(
            Order.delivery_person_id == user.id,
            Order.status.in_(['ready', 'delivering'])
        ).count()

        shift_info = None
        if user.shift_start_time and user.shift_end_time:
            shift_info = {
                'start': user.shift_start_time.strftime('%H:%M'),
                'end': user.shift_end_time.strftime('%H:%M')
            }

        notifications = NotificationRepository.get_user_notifications(user.id, limit=5)

        stores_on_map = Store.query.filter(
            Store.latitude.isnot(None),
            Store.longitude.isnot(None)
        ).all()

    except Exception as e:
        current_app.logger.exception('خطأ في تحميل لوحة المندوب')
        flash('حدث خطأ في تحميل لوحة التحكم', 'error')
        return redirect(url_for('auth.dashboard'))

    return render_template(
        'delivery/delivery_dashboard.html',
        user=user,
        orders=all_orders,
        ready_orders=ready_orders,
        delivering_orders=delivering_orders,
        delivered_orders=delivered_orders,
        status_filter=status_filter,
        allowed_statuses=allowed_statuses,
        notifications=notifications,
        map_orders=map_orders,
        shift_info=shift_info,
        active_orders_count=active_orders_count,
        stores_on_map=stores_on_map
    )

@delivery_bp.route('/delivery/orders/<int:order_id>/start', methods=['POST'])
@role_required('delivery')
def delivery_order_start(order_id):
    user = db.session.get(User, session['user_id'])
    if not user:
        return redirect(url_for('auth.login'))

    order = Order.query.get_or_404(order_id)

    try:
        OrderService.start_delivery(user, order)
        flash('تم بدء التسليم', 'success')
    except PermissionError as e:
        abort(403, description=str(e))
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('خطأ في بدء التسليم')
        flash('حدث خطأ أثناء بدء التسليم', 'error')

    return redirect(url_for('delivery.delivery_dashboard'))

@delivery_bp.route('/delivery/orders/<int:order_id>/deliver', methods=['POST'])
@role_required('delivery')
def delivery_order_deliver(order_id):
    user = db.session.get(User, session['user_id'])
    if not user:
        return redirect(url_for('auth.login'))

    order = Order.query.get_or_404(order_id)
    delivery_code = request.form.get('delivery_code', '').strip()

    try:
        OrderService.complete_delivery(user, order, delivery_code)
        flash('تم تأكيد التسليم', 'success')
    except PermissionError as e:
        abort(403, description=str(e))
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('خطأ في تأكيد التسليم')
        flash('حدث خطأ أثناء تأكيد التسليم', 'error')

    return redirect(url_for('delivery.delivery_dashboard'))

@delivery_bp.route('/delivery/availability', methods=['POST'])
@role_required('delivery')
def update_availability():
    user = db.session.get(User, session['user_id'])
    if not user:
        return redirect(url_for('auth.login'))

    is_available = request.form.get('is_available', 'false') == 'true'
    user.is_available = is_available
    db.session.commit()

    flash(f'تم تحديث حالتك إلى {"متاح" if is_available else "غير متاح"}', 'success')
    return redirect(url_for('delivery.delivery_dashboard'))

# ========== API ==========

@delivery_bp.route('/api/delivery/orders', methods=['GET'])
@token_required
def delivery_get_orders(current_user):
    if current_user.role != 'delivery':
        return jsonify({'message': 'غير مسموح'}), 403
    status = request.args.get('status')
    orders = DeliveryRepository.get_assigned_orders(current_user.id, status=status)
    return jsonify({'orders': [serialize_order(o) for o in orders]}), 200

@delivery_bp.route('/api/delivery/orders/<int:order_id>/start', methods=['POST'])
@token_required
def delivery_start_order_api(current_user, order_id):
    if current_user.role != 'delivery':
        return jsonify({'message': 'غير مسموح'}), 403
    order = Order.query.get_or_404(order_id)
    try:
        OrderService.start_delivery(current_user, order)
        return jsonify({'message': 'تم بدء التسليم'}), 200
    except PermissionError as e:
        return jsonify({'message': str(e)}), 403
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'حدث خطأ'}), 500

@delivery_bp.route('/api/delivery/orders/<int:order_id>/deliver', methods=['POST'])
@token_required
def delivery_deliver_order_api(current_user, order_id):
    if current_user.role != 'delivery':
        return jsonify({'message': 'غير مسموح'}), 403
    order = Order.query.get_or_404(order_id)
    data = request.get_json(silent=True) or {}
    code = data.get('delivery_code')
    try:
        OrderService.complete_delivery(current_user, order, code)
        return jsonify({'message': 'تم تأكيد التسليم'}), 200
    except PermissionError as e:
        return jsonify({'message': str(e)}), 403
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'حدث خطأ'}), 500

@delivery_bp.route('/api/delivery/notifications', methods=['GET'])
@login_required
def delivery_notifications_api():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'message': 'غير مسموح'}), 401
    user = db.session.get(User, user_id)
    if not user or user.role != 'delivery':
        return jsonify({'message': 'غير مسموح'}), 403
    notifs = NotificationRepository.get_user_notifications(user_id, limit=5, filter_read=False)
    data = [{'title': n.title, 'message': n.message} for n in notifs]
    return jsonify({'status': 'success', 'notifications': data}), 200
