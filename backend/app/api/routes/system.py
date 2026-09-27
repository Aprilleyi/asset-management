from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.alerts import AlertRecordList
from app.schemas.backups import BackupList, BackupRead
from app.schemas.import_export import ImportRequest, ImportResult
from app.schemas.reviews import MonthlyReviewGenerateRequest, MonthlyReviewList, MonthlyReviewRead
from app.schemas.system import DataSourceList, TaskLogList
from app.services import import_export
from app.services import reviews as review_service
from app.services import system as system_service
from app.services.backups import create_backup, list_backups


router = APIRouter(tags=["system"])


@router.get("/data-sources", response_model=DataSourceList)
def list_data_sources(session: Session = Depends(get_session)) -> DataSourceList:
    items = system_service.list_data_sources(session)
    return DataSourceList(items=items, total=len(items))


@router.get("/task-logs", response_model=TaskLogList)
def list_task_logs(session: Session = Depends(get_session)) -> TaskLogList:
    items = system_service.list_task_logs(session)
    return TaskLogList(items=items, total=len(items))


@router.get("/alerts", response_model=AlertRecordList)
def list_alert_records(session: Session = Depends(get_session)) -> AlertRecordList:
    items = system_service.list_alert_records(session)
    return AlertRecordList(items=items, total=len(items))


@router.get("/monthly-reviews", response_model=MonthlyReviewList)
def list_monthly_reviews(session: Session = Depends(get_session)) -> MonthlyReviewList:
    items = system_service.list_monthly_reviews(session)
    return MonthlyReviewList(items=items, total=len(items))


@router.post("/monthly-reviews/generate", response_model=MonthlyReviewRead)
def generate_monthly_review(
    payload: MonthlyReviewGenerateRequest,
    session: Session = Depends(get_session),
) -> MonthlyReviewRead:
    try:
        return review_service.generate_monthly_review(session, payload.reviewMonth)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/export")
def export_all_data(session: Session = Depends(get_session)) -> dict:
    return import_export.export_data(session)


@router.post("/import", response_model=ImportResult)
def import_all_data(payload: ImportRequest, session: Session = Depends(get_session)) -> ImportResult:
    try:
        counts = import_export.import_data(session, payload.data, payload.confirmOverwrite)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportResult(status="success", importedCounts=counts)


@router.get("/backups", response_model=BackupList)
def get_backups(session: Session = Depends(get_session)) -> BackupList:
    items = list_backups(session)
    return BackupList(items=items, total=len(items))


@router.post("/backups/run", response_model=BackupRead)
def run_manual_backup(session: Session = Depends(get_session)) -> BackupRead:
    try:
        return create_backup(session, backup_type="manual")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
