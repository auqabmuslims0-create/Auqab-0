from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort, jsonify, g
from database import db
from models import Order, OrderItem, Store, Notification
from sqlalchemy.orm import selectinload
from shared.time_utils import current_time
from shared.services.order_service import OrderService
from shared.services.notification_service import NotificationService
from shared.repositories.delivery_repository import DeliveryRepository
from shared.repositories.notification_repository import NotificationRepository
from shared.delivery_utils import is_delivery_available
from shared.utils import is_store_active, get_setting
from shared.decorators import role_required, api_login_required
from blueprints.api.helpers import token_required, serialize_order
import logging

logger = logging.getLogger(__name__)

# HTML/session-based routes (require CSRF on mutations)
delivery_bp = Blueprint('delivery', __name__)

# JWT-based API routes (CSRF-exempt: Bearer token in header, not cookie)
delivery_api_bp = Blueprint('delivery_api', __name__)


# ============================================================
# مساعد: استلام طلب من قائمة المتاحة (ذرّي)
# ============================================================

def _claim_order_atomic(order_id, user):
    """
    محاولة ذرّية لاستلام طلب من قائمة المتاحة.

    يعيد tuple: (success, code, order, error_msg)
      - success: bool
      - code: None | 'not_found' | 'already_claimed' | 'wrong_status'
              | 'store_unavailable' | 'not_available' | 'race_lost' | 'db_error'
      - order: Order object (أو None إن لم يُوجد)
      - error_msg: رسالة عربية للعرض

    ضمانة الذرّية:
      الـ UPDATE يشترط delivery_person_id IS NULL + status == 'ready'
      → في بيئة متزامنة، مندوبان يحاولان نفس الطلب:
        الأول ينجح (rowcount=1)، الثاني يفشل (rowcount=0).
    """
    order = db.session.get(Order, order_id)
    if not order:
        return False, 'not_found', None, 'الطلب غير موجود'

    if order.delivery_person_id is not None:
        return False, 'already_claimed', order, 'هذا الطلب مسند لمندوب آخر'

    if order.status != 'ready':
        return False, 'wrong_status', order, 'هذا الطلب ليس جاهزاً للتسليم'

    if not order.store or not order.store.has_delivery:
        return False, 'store_unavailable', order, 'هذا المتجر لا يوفر خدمة توصيل'

    if not is_store_active(order.store):
        return False, 'store_unavailable', order, 'المتجر غير نشط حالياً'

    if not is_delivery_available(user):
        return False, 'not_available', order, 'أنت غير متاح حالياً. تحقق من حالتك وورديتك.'

    # حساب رسوم التوصيل (توحيد السلوك بين view و API)
    fee_was_zero = not order.delivery_fee or order.delivery_fee == 0
    default_fee = float(get_setting('delivery_fee', 100))
    new_fee = default_fee if fee_was_zero else order.delivery_fee
    new_total = (order.total or 0) + (default_fee if fee_was_zero else 0)
    pickup_code = order.pickup_code or OrderService.generate_pickup_code()

    # ===== UPDATE ذرّي =====
    updated = Order.query.filter(
        Order.id == order_id,
        Order.delivery_person_id.is_(None),
        Order.status == 'ready'
    ).update({
        'delivery_person_id': user.id,
        'pickup_code': pickup_code,
        'delivery_fee': new_fee,
        'total': new_total,
        'updated_at': current_time(),
    }, synchronize_session=False)

    if updated == 0:
        db.session.rollback()
        return False, 'race_lost', None, 'تم استلام الطلب من مندوب آخر قبلك'

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('خطأ أثناء commit استلام الطلب')
        return False, 'db_error', None, 'حدث خطأ أثناء استلام الطلب'

    db.session.refresh(order)
    return True, None, order, None


# ============================================================
# واجهات المستخدم (Session + CSRF)
# ============================================================

@delivery_bp.route('/delivery')
@role_required('delivery')
def delivery_dashboard():
    user = g.user
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    tab = request.args.get('tab', 'mine').strip()
    if tab not in ('mine', 'available', 'map'):
        tab = 'mine'

    my_orders = Order.query.filter(
        Order.delivery_person_id == user.id,
        Order.status.in_(['ready', 'delivering'])
    ).options(
        selectinload(Order.store),
        selectinload(Order.customer),
        selectinload(Order.items).selectinload(OrderItem.product)
    ).order_by(
        db.case((Order.status == 'delivering', 0), else_=1),
        Order.created_at.asc()
    ).all()

    delivered_orders = Order.query.filter(
        Order.delivery_person_id == user.id,
        Order.status == 'delivered'
    ).options(
        selectinload(Order.store),
        selectinload(Order.customer)
    ).order_by(Order.delivered_at.desc().nullslast(), Order.created_at.desc()).limit(10).all()

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

    active_orders_count = len(my_orders)
    delivering_count = len([o for o in my_orders if o.status == 'delivering'])
    is_available_now = is_delivery_available(user)

    shift_info = None
    if user.shift_start_time and user.shift_end_time:
        shift_info = {
            'start': user.shift_start_time.strftime('%H:%M'),
            'end': user.shift_end_time.strftime('%H:%M')
        }

    active_stores = Store.query.filter(
        Store.subscription_status == 'active',
        Store.latitude.isnot(None),
        Store.longitude.isnot(None)
    ).all()

    my_map_orders = [
        o for o in my_orders
        if o.latitude is not None and o.longitude is not None
    ]

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
    user = g.user
    if not user:
        return redirect(url_for('auth.login'))

    success, code, order, err = _claim_order_atomic(order_id, user)
    if not success:
        flash(err, 'error')
        return redirect(url_for('delivery.delivery_dashboard', tab='available'))

    try:
        NotificationService.send_to_store_owner(
            order.store,
            f'المندوب {user.username} استلم الطلب رقم {order.id} من قائمة المتاحة',
            title='استلام طلب',
            link=f'/store/{order.store.id}/orders'
        )
    except Exception as e:
        logger.error(f'فشل إشعار صاحب المتجر: {e}')

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
    user = g.user
    if not user:
        return redirect(url_for('auth.login'))

    order = db.get_or_404(Order, order_id)
    pickup_code = request.form.get('pickup_code', '').strip()

    try:
        OrderService.start_delivery(user, order, pickup_code)
        flash('تم تأكيد استلام الطلب من المتجر. أنت في الطريق للزبون.', 'success')
    except PermissionError as e:
        abort(403, description=str(e))
    except ValueError as e:
        flash(str(e), 'error')
    except Exception:
        db.session.rollback()
        logger.exception('خطأ في بدء التسليم')
        flash('حدث خطأ أثناء بدء التسليم', 'error')

    return redirect(url_for('delivery.delivery_dashboard', tab='mine'))


@delivery_bp.route('/delivery/orders/<int:order_id>/deliver', methods=['POST'])
@role_required('delivery')
def delivery_order_deliver(order_id):
    """تأكيد التسليم النهائي للزبون عبر delivery_code."""
    user = g.user
    if not user:
        return redirect(url_for('auth.login'))

    order = db.get_or_404(Order, order_id)
    delivery_code = request.form.get('delivery_code', '').strip()

    try:
        OrderService.complete_delivery(user, order, delivery_code)
        flash('تم تأكيد التسليم بنجاح', 'success')
    except PermissionError as e:
        abort(403, description=str(e))
    except ValueError as e:
        flash(str(e), 'error')
    except Exception:
        db.session.rollback()
        logger.exception('خطأ في تأكيد التسليم')
        flash('حدث خطأ أثناء تأكيد التسليم', 'error')

    return redirect(url_for('delivery.delivery_dashboard', tab='mine'))


@delivery_bp.route('/delivery/availability', methods=['POST'])
@role_required('delivery')
def update_availability():
    user = g.user
    if not user:
        return redirect(url_for('auth.login'))

    is_available = request.form.get('is_available', 'false') == 'true'
    user.is_available = is_available
    db.session.commit()

    flash(f'تم تحديث حالتك إلى {"متاح" if is_available else "غير متاح"}', 'success')
    return redirect(url_for('delivery.delivery_dashboard', tab='mine'))


# ============================================================
# API للمندوبين (JWT — CSRF-exempt)
# ============================================================

@delivery_api_bp.route('/api/delivery/orders', methods=['GET'])
@token_required
def delivery_get_orders(current_user):
    if current_user.role != 'delivery':
        return jsonify({'message': 'غير مسموح'}), 403
    status = request.args.get('status')
    orders = DeliveryRepository.get_assigned_orders(current_user.id, status=status)
    return jsonify({'orders': [serialize_order(o) for o in orders.items]}), 200


@delivery_api_bp.route('/api/delivery/orders/<int:order_id>/start', methods=['POST'])
@token_required
def delivery_start_order_api(current_user, order_id):
    if current_user.role != 'delivery':
        return jsonify({'message': 'غير مسموح'}), 403
    order = db.get_or_404(Order, order_id)
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


@delivery_api_bp.route('/api/delivery/orders/<int:order_id>/deliver', methods=['POST'])
@token_required
def delivery_deliver_order_api(current_user, order_id):
    if current_user.role != 'delivery':
        return jsonify({'message': 'غير مسموح'}), 403
    order = db.get_or_404(Order, order_id)
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


@delivery_api_bp.route('/api/delivery/available-orders', methods=['GET'])
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


@delivery_api_bp.route('/api/delivery/orders/<int:order_id>/claim', methods=['POST'])
@token_required
def delivery_claim_order_api(current_user, order_id):
    if current_user.role != 'delivery':
        return jsonify({'message': 'غير مسموح'}), 403

    success, code, order, err = _claim_order_atomic(order_id, current_user)
    if not success:
        http_code = 404 if code == 'not_found' else 400
        return jsonify({'message': err}), http_code

    return jsonify({'message': 'تم استلام الطلب', 'order': serialize_order(order)}), 200


# ملاحظة: delivery_notifications_api يستخدم session auth (api_login_required)
# وليس JWT، لذا يبقى في delivery_bp (CSRF محمي على POST، لكنه GET).
@delivery_bp.route('/api/delivery/notifications', methods=['GET'])
@api_login_required
def delivery_notifications_api():
    user = g.user
    if not user or user.role != 'delivery':
        return jsonify({'message': 'غير مسموح'}), 403
    user_id = user.id
    notifs = NotificationRepository.get_user_notifications(user_id, limit=5, filter_read=False)
    data = [{'title': n.title, 'message': n.message} for n in notifs]
    return jsonify({'status': 'success', 'notifications': data}), 200
