from database import db
from models import User, Order
from shared.repositories.delivery_repository import DeliveryRepository
from shared.repositories.user_repository import UserRepository
from shared.services.user_service import UserService
from datetime import datetime

class DeliveryService:
    @staticmethod
    def toggle_delivery_person(user_id):
        person = UserRepository.get_by_id(user_id)
        if not person:
            return False, 'المستخدم غير موجود', None
        if person.role != 'delivery':
            return False, 'المستخدم ليس مندوبًا', person
        UserRepository.toggle_active(person)
        db.session.commit()
        return True, f'تم تحديث حالة المندوب {person.username}', person

    @staticmethod
    def delete_delivery_person(user_id):
        person = UserRepository.get_by_id(user_id)
        if not person:
            return False, 'المستخدم غير موجود'
        if person.role != 'delivery':
            return False, 'المستخدم ليس مندوبًا'

        # إلغاء إسناد الطلبات
        DeliveryRepository.unassign_orders(person.id)
        db.session.commit()

        # حذف شامل للمستخدم
        success, msg = UserService.delete_user_fully(person.id)
        return success, msg

    @staticmethod
    def update_shift(user_id, shift_start_str=None, shift_end_str=None, max_active_orders=None):
        person = UserRepository.get_by_id(user_id)
        if not person:
            return False, 'المستخدم غير موجود'
        try:
            shift_start_time = None
            shift_end_time = None
            if shift_start_str:
                shift_start_time = datetime.strptime(shift_start_str, '%H:%M').time()
            if shift_end_str:
                shift_end_time = datetime.strptime(shift_end_str, '%H:%M').time()
            if max_active_orders is not None:
                max_active_orders = int(max_active_orders)

            DeliveryRepository.update_shift(person, shift_start_time, shift_end_time, max_active_orders)
            db.session.commit()
            return True, 'تم تحديث الوردية'
        except Exception:
            db.session.rollback()
            return False, 'بيانات غير صالحة'
