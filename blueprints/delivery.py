from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort, jsonify, current_app
from database import db
from models import User, Order, OrderItem, Store, Notification
from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload
from shared.time_utils import current_time
from datetime import timedelta
from shared.services.order_service import OrderService
from shared.services.notification_service import NotificationService
from shared.repositories.delivery_repository import DeliveryRepository
from shared.repositories.notification_repository import NotificationRepository
from shared.repositories.user_repository import UserRepository
from shared.delivery_utils import is_delivery_available
from shared.utils import is_store_active
from shared.decorators import role_required, login_required, api_login_required
from blueprints.api.helpers import token_required, serialize_order
import logging

logger = logging.getLogger(__name__)

delivery_bp = Blueprint('delivery', __name__)


# ============================================================
# واجهات المستخدم
# ============================================================

@delivery_bp.route('/delivery')
@role_required('delivery')
def delivery_dashboard():
    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    tab = request.args.get('tab', 'mine').strip()
    if tab not in ('mine', 'available', 'map'):
        tab = 'mine'

    # ===== مهامي =====
    my_orders = Order.query.filter(
        Order.delivery_person_id == user.id,
        Order.status.in_(['ready', 'delivering'])
    ).options(
        selectinload(Order.store),
        selectinload(Order.customer),
        selectinload(Order.items).selectinload(OrderItem.product)
    ).order_by(
        # الأولوية للطلبات قيد التسليم
        db.case((Order.status == 'delivering', 0), else_=1),
        Order.created_at.asc()
    ).all()

    # آخر 10 طلبات مُسلَّمة
    delivered_orders = Order.query.filter(
        Order.delivery_person_id == user.id,
        Order.status == 'delivered'
    ).options(
        selectinload(Order.store),
        selectinload(Order.customer)
    ).order_by(Order.delivered_at.desc().nullslast(), Order.created_at.desc()).limit(10).all()

    # ===== الطلبات المتاحة في المدينة =====
    # - غير مُسندة
    # - الحالة: ready
    # - المتجر: active + has_delivery
    available_orders = Order.query.join(Store, Order.store_id == Store.id).filter(
        Order.delivery_person_id.is_(None),
        Order.status == 'ready',
        Store.has_delivery == True,
        Store.subscription_status == 'active'
    ).options(
        selectinload(Order.store),
        selectinload(Order.customer),
        selectinload(Order.items).selectinload(OrderItem.product)
    ).order_by(Order.created_at.asc()).all()

    # ===== إحصائيات =====
    active_orders_count = len(my_orders)
    delivering_count = len([o for o in my_orders if o.status == 'delivering'])
    is_available_now = is_delivery_available(user)

    shift_info = None
    if user.shift_start_time and user.shift_end_time:
        shift_info = {
            'start': user.shift_start_time.strftime('%H:%M'),
            'end': user.shift_end_time.strftime('%H:%M')
        }

    # ===== الخريطة =====
    # المتاجر النشطة (لها موقع)
    active_stores = Store.query.filter(
        Store.subscription_status == 'active',
        Store.latitude.isnot(None),
        Store.longitude.isnot(None)
    ).all()

    # طلباتي (المسندة إليّ) للموقع
    my_map_orders = [
        o for o in my_orders
        if o.latitude is not None and o.longitude is not None
    ]

    # طلبات متاحة (بدون موقع الزبون - لأنها لم تُسند بعد، لكن نعرض المتجر)
    available_map_orders = [
        o for o in available_orders
        if o.store.latitude is not None and o.store.longitude is not None
    ]

    notifications = NotificationRepository.get_user_notifications(user.id, limit=5)

    return render_template(
        'delivery/delivery_dashboard.html',
        user=user,
        tab=tab,
        my_orders=my_orders,
        delivered_orders=delivered_orders,
        available_orders=available_orders,
        active_orders_count=active_orders_count,
        delivering_count=delivering_count,
        is_available_now=is_available_now,
        shift_info=shift_info,
        active_stores=active_stores,
        my_map_orders=my_map_orders,
        available_map_orders=available_map_orders,
        notifications=notifications
    )


@delivery_bp.route('/delivery/orders/<int:order_id>/claim', methods=['POST'])
@role_required('delivery')
def delivery_claim_order(order_id):
    """E1: المندوب يستلم طلباً متاحاً من المدينة بنفسه."""
    user = db.session.get(User, session['user_id'])
    if not user:
        return redirect(url_for('auth.login'))

    order = Order.query.get_or_404(order_id)

    # تحققات
    if order.delivery_person_id is not None:
        flash('هذا الطلب مسند لمندوب آخر', 'error')
        return redirect(url_for('delivery.delivery_dashboard', tab='available'))

    if order.status != 'ready':
        flash('هذا الطلب ليس جاهزاً للتسليم', 'error')
        return redirect(url_for('delivery.delivery_dashboard', tab='available'))

    if not order.store or not order.store.has_delivery:
        flash('هذا المتجر لا يوفر خدمة توصيل', 'error')
        return redirect(url_for('delivery.delivery_dashboard', tab='available'))

    if not is_store_active(order.store):
        flash('المتجر غير نشط حالياً', 'error')
        return redirect(url_for('delivery.delivery_dashboard', tab='available'))

    if not is_delivery_available(user):
        flash('أنت غير متاح حالياً. تحقق من حالتك وورديتك.', 'error')
        return redirect(url_for('delivery.delivery_dashboard', tab='available'))

    try:
        order.delivery_person_id = user.id
        if not order.pickup_code:
            order.pickup_code = OrderService.generate_pickup_code()
        if not order.delivery_fee or order.delivery_fee == 0:
            from shared.utils import get_setting
            order.delivery_fee = float(get_setting('delivery_fee', 100))
            order.total = (order.total or 0) + order.delivery_fee
        order.updated_at = current_time()
        db.session.add(order)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('خطأ في استلام الطلب من قبل المندوب')
        flash('حدث خطأ أثناء استلام الطلب', 'error')
        return redirect(url_for('delivery.delivery_dashboard', tab='available'))

    # إشعار صاحب المتجر
    try:
        NotificationService.send_to_store_owner(
            order.store,
            f'المندوب {user.username} استلم الطلب رقم {order.id} من قائمة المتاحة',
            title='استلام طلب',
            link=f'/store/{order.store.id}/orders'
        )
    except Exception as e:
        logger.error(f'فشل إشعار صاحب المتجر: {e}')

    # إشعار الزبون
    if order.customer_id:
        try:
            NotificationService.send_to_user(
                user_id=order.customer_id,
                message=f'طلبك رقم {order.id} تم إسناده للمندوب {user.username}',
                title='المندوب في الطريق',
                link=url_for('cart.cart'),
                type_=NotificationService.TYPE_ORDER
            )
        except Exception as e:
            logger.error(f'فشل إشعار الزبون: {e}')

    flash(f'تم استلام الطلب رقم {order.id}. توجه إلى المتجر لاستلامه.', 'success')
    return redirect(url_for('delivery.delivery_dashboard', tab='mine'))


@delivery_bp.route('/delivery/orders/<int:order_id>/start', methods=['POST'])
@role_required('delivery')
def delivery_order_start(order_id):
    """S13: بدء التسليم يتطلب كود الاستلام من المتجر."""
    user = db.session.get(User, session['user_id'])
    if not user:
        return redirect(url_for('auth.login'))

    order = Order.query.get_or_404(order_id)
    pickup_code = request.form.get('pickup_code', '').strip()

    try:
        OrderService.start_delivery(user, order, pickup_code)
        flash('تم تأكيد استلام الطلب من المتجر. أنت في الطريق للزبون.', 'success')
    except PermissionError as e:
        abort(403, description=str(e))
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        db.session.rollback()
        logger.exception('خطأ في بدء التسليم')
        flash('حدث خطأ أثناء بدء التسليم', 'error')

    return redirect(url_for('delivery.delivery_dashboard', tab='mine'))


@delivery_bp.route('/delivery/orders/<int:order_id>/deliver', methods=['POST'])
@role_required('delivery')
def delivery_order_deliver(order_id):
    """تأكيد التسليم النهائي للزبون عبر delivery_code."""
    user = db.session.get(User, session['user_id'])
    if not user:
        return redirect(url_for('auth.login'))

    order = Order.query.get_or_404(order_id)
    delivery_code = request.form.get('delivery_code', '').strip()

    try:
        OrderService.complete_delivery(user, order, delivery_code)
        flash('تم تأكيد التسليم بنجاح', 'success')
    except PermissionError as e:
        abort(403, description=str(e))
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        db.session.rollback()
        logger.exception('خطأ في تأكيد التسليم')
        flash('حدث خطأ أثناء تأكيد التسليم', 'error')

    return redirect(url_for('delivery.delivery_dashboard', tab='mine'))


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
    return redirect(url_for('delivery.delivery_dashboard', tab='mine'))


# ============================================================
# API (للتطبيقات الخارجية مستقبلاً)
# ============================================================

@delivery_bp.route('/api/delivery/orders', methods=['GET'])
@token_required
def delivery_get_orders(current_user):
    if current_user.role != 'delivery':
        return jsonify({'message': 'غير مسموح'}), 403
    status = request.args.get('status')
    orders = DeliveryRepository.get_assigned_orders(current_user.id, status=status)
    return jsonify({'orders': [serialize_order(o) for o in orders.items]}), 200


@delivery_bp.route('/api/delivery/orders/<int:order_id>/start', methods=['POST'])
@token_required
def delivery_start_order_api(current_user, order_id):
    if current_user.role != 'delivery':
        return jsonify({'message': 'غير مسموح'}), 403
    order = Order.query.get_or_404(order_id)
    data = request.get_json(silent=True) or {}
    pickup_code = data.get('pickup_code')
    try:
        OrderService.start_delivery(current_user, order, pickup_code)
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


@delivery_bp.route('/api/delivery/available-orders', methods=['GET'])
@token_required
def delivery_available_orders_api(current_user):
    if current_user.role != 'delivery':
        return jsonify({'message': 'غير مسموح'}), 403
    orders = Order.query.join(Store, Order.store_id == Store.id).filter(
        Order.delivery_person_id.is_(None),
        Order.status == 'ready',
        Store.has_delivery == True,
        Store.subscription_status == 'active'
    ).order_by(Order.created_at.asc()).all()
    return jsonify({'orders': [serialize_order(o) for o in orders]}), 200


@delivery_bp.route('/api/delivery/orders/<int:order_id>/claim', methods=['POST'])
@token_required
def delivery_claim_order_api(current_user, order_id):
    if current_user.role != 'delivery':
        return jsonify({'message': 'غير مسموح'}), 403
    order = Order.query.get_or_404(order_id)
    if order.delivery_person_id is not None:
        return jsonify({'message': 'الطلب مسند لمندوب آخر'}), 400
    if order.status != 'ready':
        return jsonify({'message': 'الطلب ليس جاهزاً للتسليم'}), 400
    if not is_delivery_available(current_user):
        return jsonify({'message': 'أنت غير متاح حالياً'}), 400
    try:
        order.delivery_person_id = current_user.id
        if not order.pickup_code:
            order.pickup_code = OrderService.generate_pickup_code()
        order.updated_at = current_time()
        db.session.add(order)
        db.session.commit()
        return jsonify({'message': 'تم استلام الطلب', 'order': serialize_order(order)}), 200
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'حدث خطأ'}), 500


@delivery_bp.route('/api/delivery/notifications', methods=['GET'])
@api_login_required
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
