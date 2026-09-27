from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.alert_rules import AlertRuleList, AlertRuleRead, AlertRuleUpdate
from app.services import alert_rules as alert_rule_service


router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])


@router.get("", response_model=AlertRuleList)
def list_alert_rules(session: Session = Depends(get_session)) -> AlertRuleList:
    items = alert_rule_service.list_alert_rules(session)
    return AlertRuleList(items=items, total=len(items))


@router.patch("/{rule_code}", response_model=AlertRuleRead)
def update_alert_rule(
    rule_code: str,
    payload: AlertRuleUpdate,
    session: Session = Depends(get_session),
) -> AlertRuleRead:
    return alert_rule_service.update_alert_rule(session, rule_code, payload)
