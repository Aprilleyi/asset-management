from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.task_runner import run_task_with_new_session
from app.core.config import settings


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)
    _register_jobs(scheduler)
    return scheduler


def _register_jobs(scheduler: BackgroundScheduler) -> None:
    scheduler.add_job(
        run_task_with_new_session,
        CronTrigger(hour=20, minute=30, timezone=settings.scheduler_timezone),
        args=["price_update", scheduler],
        id="price_update_2030",
        replace_existing=True,
    )
    scheduler.add_job(
        run_task_with_new_session,
        CronTrigger(hour=22, minute=30, timezone=settings.scheduler_timezone),
        args=["price_update", scheduler],
        id="price_update_2230",
        replace_existing=True,
    )
    scheduler.add_job(
        run_task_with_new_session,
        CronTrigger(hour=23, minute=0, timezone=settings.scheduler_timezone),
        args=["price_update", scheduler],
        id="price_update_2300",
        replace_existing=True,
    )
    scheduler.add_job(
        run_task_with_new_session,
        CronTrigger(hour=23, minute=30, timezone=settings.scheduler_timezone),
        args=["daily_snapshot", scheduler],
        id="daily_snapshot_2330",
        replace_existing=True,
    )
    scheduler.add_job(
        run_task_with_new_session,
        CronTrigger(hour=22, minute=40, timezone=settings.scheduler_timezone),
        args=["alert_generate", scheduler],
        id="alert_generate_2240",
        replace_existing=True,
    )
    scheduler.add_job(
        run_task_with_new_session,
        CronTrigger(hour=8, minute=0, timezone=settings.scheduler_timezone),
        args=["data_source_check", scheduler],
        id="data_source_check_0800",
        replace_existing=True,
    )
    scheduler.add_job(
        run_task_with_new_session,
        CronTrigger(hour=0, minute=30, timezone=settings.scheduler_timezone),
        args=["auto_backup", scheduler],
        id="auto_backup_0030",
        replace_existing=True,
    )
