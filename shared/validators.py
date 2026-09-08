import re
import string
from datetime import datetime

def is_valid_email(email):
    """التحقق من صحة البريد الإلكتروني."""
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_valid_phone_syrian(phone):
    """التحقق من رقم هاتف سوري (9 أرقام يبدأ بـ 9)."""
    if not phone:
        return False
    phone = phone.strip()
    if phone.startswith('+963'):
        phone = phone[4:]
    elif phone.startswith('963'):
        phone = phone[3:]
    elif phone.startswith('0'):
        phone = phone[1:]
    return len(phone) == 9 and phone.startswith('9') and phone.isdigit()

def is_valid_phone_general(phone):
    """التحقق من رقم هاتف عام (أرقام فقط مع إمكانية +)."""
    if not phone:
        return False
    pattern = r'^\+?[0-9]{8,15}$'
    return re.match(pattern, phone.strip()) is not None

def is_strong_password(password):
    """التحقق من قوة كلمة المرور: طول >=8، حرف كبير، حرف صغير، رقم، رمز خاص."""
    if not password:
        return False, 'كلمة المرور مطلوبة'
    if len(password) < 8:
        return False, 'كلمة المرور يجب أن تكون 8 أحرف على الأقل'
    if not any(c.isupper() for c in password):
        return False, 'كلمة المرور يجب أن تحتوي على حرف كبير (A-Z)'
    if not any(c.islower() for c in password):
        return False, 'كلمة المرور يجب أن تحتوي على حرف صغير (a-z)'
    if not any(c.isdigit() for c in password):
        return False, 'كلمة المرور يجب أن تحتوي على رقم (0-9)'
    if not any(c in string.punctuation for c in password):
        return False, 'كلمة المرور يجب أن تحتوي على رمز خاص مثل !@#$%^&*()'
    return True, ''

def is_valid_username(username):
    """التحقق من اسم مستخدم صالح (أحرف وأرقام وشرطة سفلية، طول 3-20)."""
    if not username:
        return False, 'اسم المستخدم مطلوب'
    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
        return False, 'اسم المستخدم يجب أن يكون 3-20 حرفًا (أحرف إنجليزية وأرقام وشرطة سفلية)'
    return True, ''

def is_valid_store_name(name):
    """التحقق من اسم متجر صالح (طول 3-100)."""
    if not name or len(name.strip()) < 3 or len(name.strip()) > 100:
        return False, 'اسم المتجر يجب أن يكون بين 3 و 100 حرف'
    return True, ''

def is_valid_product_name(name):
    """التحقق من اسم منتج صالح (طول 2-120)."""
    if not name or len(name.strip()) < 2 or len(name.strip()) > 120:
        return False, 'اسم المنتج يجب أن يكون بين 2 و 120 حرف'
    return True, ''

def is_valid_public_id(public_id):
    """التحقق من معرف عام بصيغة A-XXXX-XXXX."""
    if not public_id:
        return False
    pattern = r'^A-[A-Z0-9]{4}-[A-Z0-9]{4}$'
    return re.match(pattern, public_id.strip()) is not None

def is_valid_color(color):
    """التحقق من لون بصيغة hex (#RRGGBB)."""
    if not color:
        return False
    pattern = r'^#(?:[0-9a-fA-F]{3}){1,2}$'
    return re.match(pattern, color.strip()) is not None

def is_valid_time(time_str):
    """التحقق من وقت بصيغة HH:MM."""
    if not time_str:
        return False
    try:
        datetime.strptime(time_str, '%H:%M')
        return True
    except ValueError:
        return False

def is_valid_latitude(value):
    """التحقق من خط عرض صالح (-90 إلى 90)."""
    try:
        lat = float(value)
        return -90 <= lat <= 90
    except (ValueError, TypeError):
        return False

def is_valid_longitude(value):
    """التحقق من خط طول صالح (-180 إلى 180)."""
    try:
        lng = float(value)
        return -180 <= lng <= 180
    except (ValueError, TypeError):
        return False

def is_valid_quantity(qty):
    """التحقق من كمية صالحة (عدد صحيح موجب)."""
    try:
        q = int(qty)
        return q > 0
    except (ValueError, TypeError):
        return False

def is_valid_price(price):
    """التحقق من سعر صالح (عدد غير سالب)."""
    try:
        p = float(price)
        return p >= 0
    except (ValueError, TypeError):
        return False

def is_valid_date(date_str, format='%Y-%m-%d'):
    """التحقق من تاريخ صالح بصيغة معينة."""
    if not date_str:
        return False
    try:
        datetime.strptime(date_str, format)
        return True
    except ValueError:
        return False

def validate_required_fields(data, required_fields):
    """
    التحقق من وجود جميع الحقول المطلوبة في قاموس.
    يرجع (success, error_message) حيث error_message قائمة بالحقول الناقصة.
    """
    missing = [field for field in required_fields if field not in data or data[field] is None or (isinstance(data[field], str) and not data[field].strip())]
    if missing:
        return False, f"الحقول التالية مطلوبة: {', '.join(missing)}"
    return True, ''
