from database import db
from models import Payment
from shared.repositories.payment_repository import PaymentRepository
from shared.time_utils import current_time

class PaymentService:
    @staticmethod
    def create_payment(user_id, amount, method='cash', order_id=None, store_id=None, subscription_id=None,
                       reference=None, proof_image=None, notes=None):
        if amount <= 0:
            return None, 'المبلغ يجب أن يكون أكبر من صفر'
        allowed_methods = ['cash', 'wallet', 'bank_transfer', 'manual_delivery']
        if method not in allowed_methods:
            method = 'cash'
        if not user_id:
            return None, 'معرف المستخدم مطلوب'

        payment = PaymentRepository.create({
            'user_id': user_id,
            'order_id': order_id,
            'store_id': store_id,
            'subscription_id': subscription_id,
            'amount': amount,
            'method': method,
            'status': 'pending',
            'reference': reference,
            'proof_image': proof_image,
            'notes': notes
        })
        db.session.add(payment)
        return payment, None

    @staticmethod
    def update_payment_status(payment_id, new_status):
        payment = PaymentRepository.get_by_id(payment_id)
        if not payment:
            return False, 'الدفع غير موجود'
        if new_status not in ['pending', 'paid', 'failed', 'refunded']:
            return False, 'حالة غير صالحة'
        payment.status = new_status
        payment.updated_at = current_time()
        try:
            db.session.commit()
            return True, 'تم تحديث حالة الدفع'
        except Exception:
            db.session.rollback()
            return False, 'حدث خطأ أثناء تحديث حالة الدفع'

    @staticmethod
    def get_payment_by_subscription(subscription_id):
        return PaymentRepository.get_by_subscription(subscription_id)

    @staticmethod
    def get_payment_by_order(order_id):
        return PaymentRepository.get_by_order(order_id)

    @staticmethod
    def get_all_payments(status=None, method=None, page=1, per_page=20):
        return PaymentRepository.get_all_payments(page=page, per_page=per_page, status=status, method=method)
