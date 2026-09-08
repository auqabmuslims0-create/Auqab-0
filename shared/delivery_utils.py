from models import Order
from shared.time_utils import current_time


def is_delivery_available(user):
    """التحقق من أن المندوب متاح حاليًا حسب الوردية وعدد الطلبات النشطة."""
    if not user or user.role != 'delivery' or not user.is_active:
        return False

    # الإصلاح: التأكد من أن المندوب قام بتعيين نفسه متاحاً
    if not user.is_available:
        return False

    # التحقق من الوردية الزمنية
    if user.shift_start_time and user.shift_end_time:
        now_time = current_time().time()
        if user.shift_start_time < user.shift_end_time:
            if not (user.shift_start_time <= now_time < user.shift_end_time):
                return False
        else:
            # وردية عابرة لليوم التالي
            if not (now_time >= user.shift_start_time or now_time < user.shift_end_time):
                return False

    # التحقق من عدد الطلبات النشطة
    active_count = Order.query.filter(
        Order.delivery_person_id == user.id,
        Order.status.in_(['ready', 'delivering'])
    ).count()

    max_orders = user.max_active_orders
    # إذا كانت max_orders غير محددة أو <=0 نعتبرها غير محدودة (لا نمنع)
    if max_orders is not None and max_orders > 0 and active_count >= max_orders:
        return False

    return True
