from flask import request, jsonify
from database import db
from models import Order, Product
from shared.services.order_service import OrderService
from . import api_bp
from .helpers import token_required, serialize_order

@api_bp.route('/orders', methods=['POST'])
@token_required
def create_order(current_user):
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'message': 'يجب إرسال البيانات بصيغة JSON'}), 400

    items_data = data.get('items')
    delivery_address = data.get('delivery_address', '').strip()
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    if not items_data or not isinstance(items_data, list) or len(items_data) == 0:
        return jsonify({'message': 'يجب توفير عناصر الطلب'}), 400

    store = None
    for item in items_data:
        product_id = item.get('product_id')
        if product_id:
            product = db.session.get(Product, product_id)
            if product:
                store = product.store
                break
    if not store:
        return jsonify({'message': 'المتجر غير موجود'}), 400

    try:
        order = OrderService.create_order(
            user=current_user,
            store=store,
            items_data=items_data,
            delivery_address=delivery_address,
            latitude=latitude,
            longitude=longitude,
            payment_method='cash'
        )
        return jsonify({'message': 'تم تقديم الطلب بنجاح', 'order': serialize_order(order)}), 201
    except ValueError as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 400
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'حدث خطأ أثناء إنشاء الطلب'}), 500

@api_bp.route('/orders', methods=['GET'])
@token_required
def get_orders(current_user):
    orders = Order.query.filter_by(customer_id=current_user.id).order_by(Order.created_at.desc()).all()
    return jsonify({'orders': [serialize_order(o) for o in orders]}), 200

@api_bp.route('/orders/<int:order_id>', methods=['GET'])
@token_required
def get_order(current_user, order_id):
    order = Order.query.get_or_404(order_id)
    if order.customer_id != current_user.id:
        return jsonify({'message': 'غير مسموح'}), 403
    return jsonify({'order': serialize_order(order)}), 200

@api_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
@token_required
def cancel_order(current_user, order_id):
    order = Order.query.get_or_404(order_id)
    try:
        OrderService.cancel_order(current_user, order)
        return jsonify({'message': 'تم إلغاء الطلب بنجاح', 'order': serialize_order(order)}), 200
    except PermissionError as e:
        return jsonify({'message': str(e)}), 403
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'حدث خطأ أثناء إلغاء الطلب'}), 500
