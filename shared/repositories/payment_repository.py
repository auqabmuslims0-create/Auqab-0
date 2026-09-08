from database import db
from models import Payment
from sqlalchemy.orm import joinedload

class PaymentRepository:
    @staticmethod
    def create(payment_data):
        payment = Payment(**payment_data)
        db.session.add(payment)
        return payment

    @staticmethod
    def get_by_id(payment_id):
        return db.session.get(Payment, payment_id)

    @staticmethod
    def get_by_order(order_id):
        return Payment.query.filter_by(order_id=order_id).all()

    @staticmethod
    def get_by_subscription(subscription_id):
        return Payment.query.filter_by(subscription_id=subscription_id).all()

    @staticmethod
    def get_all_payments(page=1, per_page=20, status=None, method=None):
        query = Payment.query.options(
            joinedload(Payment.user),
            joinedload(Payment.order),
            joinedload(Payment.store),
            joinedload(Payment.subscription)
        )
        if status:
            query = query.filter(Payment.status == status)
        if method:
            query = query.filter(Payment.method == method)
        return query.order_by(Payment.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def update_status(payment, new_status):
        payment.status = new_status
        payment.updated_at = db.func.now()
        db.session.add(payment)
