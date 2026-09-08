from database import db
from models import Order, OrderItem, OrderStatusHistory
from sqlalchemy import func

class OrderRepository:
    @staticmethod
    def get_by_id(order_id):
        return db.session.get(Order, order_id)

    @staticmethod
    def create_order(order_data):
        order = Order(**order_data)
        db.session.add(order)
        return order

    @staticmethod
    def add_item(order_id, product_id, quantity, price, options_selected=None):
        item = OrderItem(
            order_id=order_id,
            product_id=product_id,
            quantity=quantity,
            price=price,
            options_selected=options_selected
        )
        db.session.add(item)
        return item

    @staticmethod
    def add_status_history(order_id, from_status, to_status, changed_by, note=''):
        history = OrderStatusHistory(
            order_id=order_id,
            from_status=from_status,
            to_status=to_status,
            changed_by=changed_by,
            note=note
        )
        db.session.add(history)
        return history

    @staticmethod
    def update_order(order):
        db.session.add(order)

    @staticmethod
    def get_orders_by_customer(customer_id, page=1, per_page=20, status=None):
        query = Order.query.filter_by(customer_id=customer_id)
        if status:
            query = query.filter(Order.status == status)
        return query.order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_orders_by_store(store_id, page=1, per_page=20, status=None):
        query = Order.query.filter_by(store_id=store_id)
        if status:
            query = query.filter(Order.status == status)
        return query.order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_orders_by_delivery_person(delivery_person_id, page=1, per_page=20, status=None):
        query = Order.query.filter_by(delivery_person_id=delivery_person_id)
        if status:
            query = query.filter(Order.status == status)
        return query.order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_all_orders(page=1, per_page=20, status=None, store_id=None, customer_id=None):
        query = Order.query
        if status:
            query = query.filter(Order.status == status)
        if store_id:
            query = query.filter(Order.store_id == store_id)
        if customer_id:
            query = query.filter(Order.customer_id == customer_id)
        return query.order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
