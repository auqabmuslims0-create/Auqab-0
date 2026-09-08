from database import db
from models import User, Order

class DeliveryRepository:
    @staticmethod
    def get_delivery_person_by_id(user_id):
        return db.session.get(User, user_id)

    @staticmethod
    def get_delivery_persons():
        return User.query.filter_by(role='delivery').all()

    @staticmethod
    def get_available_delivery_persons():
        # يمكن إضافة منطق التوفر لاحقاً
        return User.query.filter_by(role='delivery', is_active=True, is_available=True).all()

    @staticmethod
    def update_shift(person, shift_start_time, shift_end_time, max_active_orders):
        person.shift_start_time = shift_start_time
        person.shift_end_time = shift_end_time
        person.max_active_orders = max_active_orders
        db.session.add(person)

    @staticmethod
    def get_assigned_orders(delivery_person_id, page=1, per_page=20, status=None):
        query = Order.query.filter_by(delivery_person_id=delivery_person_id)
        if status:
            query = query.filter(Order.status == status)
        return query.order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def unassign_orders(delivery_person_id):
        orders = Order.query.filter_by(delivery_person_id=delivery_person_id).all()
        for order in orders:
            order.delivery_person_id = None
            order.delivery_fee = 0.0
            db.session.add(order)
