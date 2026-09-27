from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from apscheduler.triggers.date import DateTrigger
from sqlmodel import Session, select

from app.core.config import settings
from app.data_sources.akshare_adapter import AkShareAdapter
from app.db.session import engine
from app.models import DataSource, TaskLog
from app.schemas.tasks import TaskRunResponse, TaskStatusRead
from app.services.alerts import generate_alerts
from app.services.backups import create_backup
from app.services.ids import make_id
from app.services.prices import run_price_update
from app.services.snapshots import create_daily_snapshot
from app.services.transactions import generate_due_dca_transactions


TASK_NAMES = {
    "price_update": "行情更新",
    "alert_generate": "提醒生成",
    "daily_snapshot": "每日快照",
    "data_source_check": "数据源健康检查",
    "auto_backup": "自动备份",
}

MAX_RETRY_COUNT = 3
RETRY_DELAY_MINUTES = 30


def run_task(session: Session, task_type: str, scheduler=None, retry_count: int = 0) -> TaskRunResponse:
    if task_type not in TASK_NAMES:
        raise ValueError(f"Unsupported task type: {task_type}")
    if task_type == "price_update":
        generate_due_dca_transactions(session)
        result = run_price_update(session)
        if result.status in {"success", "partial_success"}:
            run_task(session, "alert_generate", scheduler=scheduler)
        elif result.status == "failed":
            _schedule_retry(scheduler, task_type, retry_count)
        return TaskRunResponse(
            taskLogId=result.taskLogId,
            taskType=task_type,
            status=result.status,
            message=f"行情更新完成：成功 {result.successCount}，失败 {result.failedCount}",
            errorMessage=None,
            successCount=result.successCount,
            failedCount=result.failedCount,
        )
    return _run_logged_task(session, task_type, _task_callable(task_type), scheduler, retry_count)


def run_task_with_new_session(task_type: str, scheduler=None, retry_count: int = 0) -> None:
    with Session(engine) as session:
        run_task(session, task_type, scheduler=scheduler, retry_count=retry_count)


def list_task_statuses(session: Session, scheduler=None) -> list[TaskStatusRead]:
    statuses = []
    for task_type, task_name in TASK_NAMES.items():
        last_log = session.exec(
            select(TaskLog)
            .where(TaskLog.ownerId == settings.default_owner_id, TaskLog.taskType == task_type)
            .order_by(TaskLog.startedAt.desc())
        ).first()
        statuses.append(
            TaskStatusRead(
                taskType=task_type,
                taskName=task_name,
                isEnabled=settings.scheduler_enabled,
                lastRunAt=last_log.startedAt if last_log else None,
                nextRunAt=_next_run_at(scheduler, task_type),
                lastStatus=last_log.status if last_log else None,
                lastMessage=last_log.message if last_log else None,
                errorMessage=last_log.errorMessage if last_log else None,
            )
        )
    return statuses


def _run_logged_task(
    session: Session,
    task_type: str,
    func: Callable[[Session], tuple[int, int, str]],
    scheduler=None,
    retry_count: int = 0,
) -> TaskRunResponse:
    started_at = _now()
    task_log = TaskLog(
        id=make_id("tasklog"),
        ownerId=settings.default_owner_id,
        taskType=task_type,
        taskName=TASK_NAMES[task_type],
        status="running",
        startedAt=started_at,
    )
    session.add(task_log)
    session.commit()
    session.refresh(task_log)
    try:
        success_count, failed_count, message = func(session)
        status = _task_status(success_count, failed_count)
        task_log.status = status
        task_log.message = message
        task_log.successCount = success_count
        task_log.failedCount = failed_count
        task_log.skippedCount = 0
        task_log.errorMessage = None
    except Exception as exc:
        task_log.status = "failed"
        task_log.message = None
        task_log.successCount = 0
        task_log.failedCount = 1
        task_log.skippedCount = 0
        task_log.errorMessage = str(exc)
        _schedule_retry(scheduler, task_type, retry_count)
    task_log.finishedAt = _now()
    task_log.durationMs = int((task_log.finishedAt - started_at).total_seconds() * 1000)
    task_log.nextRunAt = _next_run_at(scheduler, task_type)
    session.add(task_log)
    session.commit()
    session.refresh(task_log)
    return TaskRunResponse(
        taskLogId=task_log.id,
        taskType=task_type,
        status=task_log.status,
        message=task_log.message,
        errorMessage=task_log.errorMessage,
        successCount=task_log.successCount or 0,
        failedCount=task_log.failedCount or 0,
    )


def _task_callable(task_type: str) -> Callable[[Session], tuple[int, int, str]]:
    return {
        "alert_generate": _run_alert_generate,
        "daily_snapshot": _run_daily_snapshot,
        "data_source_check": _run_data_source_check,
        "auto_backup": _run_auto_backup,
    }[task_type]


def _run_alert_generate(session: Session) -> tuple[int, int, str]:
    count = generate_alerts(session)
    return count, 0, f"提醒生成完成：新增或更新 {count} 条"


def _run_daily_snapshot(session: Session) -> tuple[int, int, str]:
    snapshot = create_daily_snapshot(session)
    return 1, 0, f"每日快照已生成：{snapshot.snapshotDate}"


def _run_data_source_check(session: Session) -> tuple[int, int, str]:
    success_count = 0
    failed_count = 0
    now = _now()
    data_sources = list(session.exec(select(DataSource).where(DataSource.ownerId == settings.default_owner_id)).all())
    for source in data_sources:
        if source.sourceType == "manual":
            source.healthStatus = "normal"
            source.lastSuccessAt = now
            source.lastErrorMessage = None
            success_count += 1
        elif source.sourceType == "akshare":
            try:
                AkShareAdapter()
                source.healthStatus = "normal"
                source.lastSuccessAt = now
                source.lastErrorMessage = None
                success_count += 1
            except Exception as exc:
                source.healthStatus = "abnormal"
                source.lastFailedAt = now
                source.lastErrorMessage = str(exc)
                failed_count += 1
        session.add(source)
    session.commit()
    return success_count, failed_count, f"数据源检查完成：正常 {success_count}，异常 {failed_count}"


def _run_auto_backup(session: Session) -> tuple[int, int, str]:
    backup = create_backup(session, backup_type="auto")
    return 1, 0, f"自动备份已生成：{backup.fileName}"


def _schedule_retry(scheduler, task_type: str, retry_count: int) -> None:
    if not settings.scheduler_enabled or not scheduler or not scheduler.running or retry_count >= MAX_RETRY_COUNT:
        return
    run_at = _now() + timedelta(minutes=RETRY_DELAY_MINUTES)
    scheduler.add_job(
        run_task_with_new_session,
        trigger=DateTrigger(run_date=run_at),
        args=[task_type, scheduler, retry_count + 1],
        id=f"{task_type}_retry_{retry_count + 1}_{int(run_at.timestamp())}",
        replace_existing=True,
    )


def _next_run_at(scheduler, task_type: str) -> Optional[datetime]:
    if not settings.scheduler_enabled or not scheduler or not scheduler.running:
        return None
    next_runs = [
        job.next_run_time
        for job in scheduler.get_jobs()
        if job.id.startswith(task_type) and job.next_run_time is not None
    ]
    return min(next_runs) if next_runs else None


def _task_status(success_count: int, failed_count: int) -> str:
    if failed_count == 0:
        return "success"
    if success_count > 0:
        return "partial_success"
    return "failed"


def _now() -> datetime:
    return datetime.now(timezone.utc)
