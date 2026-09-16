from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    _DAMASCUS_TZ = ZoneInfo("Asia/Damascus")
except Exception:
    _DAMASCUS_TZ = None


def current_time():
    """
    إرجاع الوقت الحالي بتوقيت دمشق (Asia/Damascus) ككائن naive.

    - يستخدم zoneinfo لاحترام التوقيت الصيفي تلقائياً.
    - يعيد naive datetime لأن أعمدة DB من نوع TIMESTAMP WITHOUT TIME ZONE.
    - إذا لم يتوفر tzdata، يستخدم UTC+3 ثابتاً كـ fallback.
    """
    if _DAMASCUS_TZ is not None:
        return datetime.now(_DAMASCUS_TZ).replace(tzinfo=None)
    return (datetime.now(timezone.utc) + timedelta(hours=3)).replace(tzinfo=None)
