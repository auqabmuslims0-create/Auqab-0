from datetime import datetime, timedelta, timezone

def current_time():
    """إرجاع الوقت الحالي بتوقيت سوريا (Asia/Damascus) ككائن naive."""
    # سوريا تسبق UTC بثلاث ساعات (بدون توقيت صيفي)
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=3)
