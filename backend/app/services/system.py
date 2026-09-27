from sqlmodel import Session, select

from app.core.config import settings
from app.models import AlertRecord, DataSource, MonthlyReview, TaskLog


def list_data_sources(session: Session) -> list[DataSource]:
    return list(
        session.exec(
            select(DataSource)
            .where(DataSource.ownerId == settings.default_owner_id)
            .order_by(DataSource.priority)
        ).all()
    )


def list_task_logs(session: Session) -> list[TaskLog]:
    return list(
        session.exec(
            select(TaskLog)
            .where(TaskLog.ownerId == settings.default_owner_id)
            .order_by(TaskLog.createdAt.desc())
        ).all()
    )


def list_alert_records(session: Session) -> list[AlertRecord]:
    return list(
        session.exec(
            select(AlertRecord)
            .where(AlertRecord.ownerId == settings.default_owner_id)
            .order_by(AlertRecord.triggeredAt.desc())
        ).all()
    )


def list_monthly_reviews(session: Session) -> list[MonthlyReview]:
    return list(
        session.exec(
            select(MonthlyReview)
            .where(MonthlyReview.ownerId == settings.default_owner_id)
            .order_by(MonthlyReview.reviewMonth.desc())
        ).all()
    )
