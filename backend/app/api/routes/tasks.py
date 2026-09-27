from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.prices import PriceUpdateRunResult
from app.schemas.tasks import TaskRunResponse, TaskStatusList
from app.services.prices import run_price_update
from app.services.task_runner import list_task_statuses, run_task
from app.tasks.registry import scheduler


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/price-update/run", response_model=PriceUpdateRunResult)
def run_price_update_task(session: Session = Depends(get_session)) -> PriceUpdateRunResult:
    result = run_price_update(session)
    if result.status in {"success", "partial_success"}:
        run_task(session, "alert_generate", scheduler=scheduler)
    return result


@router.get("/status", response_model=TaskStatusList)
def task_statuses(session: Session = Depends(get_session)) -> TaskStatusList:
    items = list_task_statuses(session, scheduler=scheduler)
    return TaskStatusList(items=items, total=len(items))


@router.post("/{task_type}/run", response_model=TaskRunResponse)
def run_task_now(task_type: str, session: Session = Depends(get_session)) -> TaskRunResponse:
    try:
        return run_task(session, task_type, scheduler=scheduler)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
