import logging
import os
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = None

def init_scheduler(app):
    """تهيئة المجدول الدوري لتنفيذ مهام الصيانة."""
    global scheduler
    if scheduler and scheduler.running:
        return scheduler

    # التحقق من تفعيل المجدول عبر متغير البيئة أو إعداد التطبيق
    enabled = app.config.get('SCHEDULER_ENABLED', False) or os.environ.get('SCHEDULER_ENABLED', '0') == '1'
    if not enabled:
        app.logger.info('تم تعطيل المجدول (SCHEDULER_ENABLED=0)')
        return None

    scheduler = BackgroundScheduler(
        timezone='UTC',
        daemon=True
    )

    from shared.services.subscription_service import SubscriptionService

    def subscription_tasks():
        try:
            with app.app_context():
                expiring = SubscriptionService.check_expiring_subscriptions(days=3)
                expired = SubscriptionService.expire_subscriptions()
                app.logger.info(f'مهام الاشتراكات: تم تنبيه {expiring} اشتراك قارب على الانتهاء، وتم تحديث {expired} اشتراك منتهي')
        except Exception as e:
            app.logger.error(f'فشل تنفيذ مهام الاشتراكات: {str(e)}')

    # جدولة المهمة كل ساعة (يمكن تغييرها إلى يوميًا إذا لزم)
    scheduler.add_job(
        subscription_tasks,
        trigger=IntervalTrigger(hours=1),
        id='subscription_maintenance',
        name='فحص الاشتراكات وتنبيهاتها',
        replace_existing=True,
        max_instances=1,
        coalesce=True
    )

    scheduler.start()
    app.logger.info('تم بدء المجدول الدوري')

    # تسجيل دالة الإيقاف عند الخروج
    atexit.register(shutdown_scheduler)

    return scheduler

def shutdown_scheduler():
    """إيقاف المجدول بأمان عند إيقاف التطبيق."""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        scheduler = None
        logger.info('تم إيقاف المجدول')
