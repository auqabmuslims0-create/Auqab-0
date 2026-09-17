import logging
import os
import atexit
import fcntl
import tempfile
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = None


def _get_lock_path(app):
    """مسار ملف القفل المشترك بين workers."""
    return os.path.join(tempfile.gettempdir(), 'husayniyyah_scheduler.lock')


def _acquire_nonblocking_lock(lock_file_handle):
    """
    محاولة الحصول على قفل حصري غير معطّل (non-blocking).
    يعيد True إن نجح، False إن كان مشغولاً (worker آخر ينفذ المهمة).
    """
    try:
        fcntl.flock(lock_file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (BlockingIOError, OSError):
        return False


def _release_lock(lock_file_handle):
    try:
        fcntl.flock(lock_file_handle.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass


def init_scheduler(app):
    """
    تهيئة المجدول الدوري لتنفيذ مهام الصيانة.

    ملاحظة: مع gunicorn --workers N، يُشغَّل هذا في كل worker.
    لتفادي التنفيذ المزدوج لمهام الاشتراكات، نستخدم file lock
    (fcntl.flock) حول جسم المهمة — worker واحد فقط ينفذها في كل دورة.
    """
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

    lock_path = _get_lock_path(app)

    def subscription_tasks():
        # قفل حصري غير معطّل — worker واحد فقط ينفذ
        try:
            lock_handle = open(lock_path, 'w')
        except Exception as e:
            app.logger.error(f'تعذر فتح ملف القفل {lock_path}: {e}')
            return

        try:
            if not _acquire_nonblocking_lock(lock_handle):
                app.logger.info('مهمة الاشتراكات تعمل في worker آخر — تخطي هذه الدورة')
                return

            try:
                with app.app_context():
                    expiring = SubscriptionService.check_expiring_subscriptions(days=3)
                    expired = SubscriptionService.expire_subscriptions()
                    app.logger.info(
                        f'مهام الاشتراكات: تم تنبيه {expiring} اشتراك قارب على الانتهاء، '
                        f'وتم تحديث {expired} اشتراك منتهي'
                    )
            except Exception as e:
                app.logger.error(f'فشل تنفيذ مهام الاشتراكات: {str(e)}')
            finally:
                _release_lock(lock_handle)
        finally:
            try:
                lock_handle.close()
            except Exception:
                pass

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
    app.logger.info(f'تم بدء المجدول الدوري (lock={lock_path})')

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
