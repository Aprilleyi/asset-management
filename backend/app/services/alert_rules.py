from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlmodel import Session, select

from app.core.config import settings
from app.core.errors import not_found, validation_error
from app.models import AlertRule
from app.schemas.alert_rules import AlertRuleUpdate


ALERT_LEVELS = {"strong", "must", "attention", "review"}


def list_alert_rules(session: Session) -> list[AlertRule]:
    statement = select(AlertRule).where(AlertRule.ownerId == settings.default_owner_id)
    return list(session.exec(statement.order_by(AlertRule.category, AlertRule.ruleCode)).all())


def update_alert_rule(session: Session, rule_code: str, payload: AlertRuleUpdate) -> AlertRule:
    rule = _get_rule_by_code(session, rule_code)
    if not rule.isEditable:
        raise validation_error("Alert rule is not editable")

    data = payload.model_dump(exclude_unset=True)
    if "alertLevel" in data and data["alertLevel"] not in ALERT_LEVELS:
        raise validation_error("alertLevel must be one of strong, must, attention, review")
    if "thresholdValue" in data:
        _validate_threshold(data["thresholdValue"])
    if "repeatIntervalDays" in data and data["repeatIntervalDays"] is not None and data["repeatIntervalDays"] < 0:
        raise validation_error("repeatIntervalDays must be greater than or equal to 0")

    for key, value in data.items():
        setattr(rule, key, value)
    rule.updatedAt = datetime.now(timezone.utc)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


def _get_rule_by_code(session: Session, rule_code: str) -> AlertRule:
    statement = select(AlertRule).where(
        AlertRule.ownerId == settings.default_owner_id,
        AlertRule.ruleCode == rule_code,
    )
    rule = session.exec(statement).first()
    if not rule:
        raise not_found("Alert rule not found")
    return rule


def _validate_threshold(value: str) -> None:
    if value == "":
        raise validation_error("thresholdValue cannot be empty")
    normalized = str(value).lower()
    if normalized in {"true", "false", "normal", "delayed", "abnormal", "failed", "manual", "missing"}:
        return
    try:
        Decimal(str(value))
    except InvalidOperation as exc:
        raise validation_error("thresholdValue must be a number or supported status value") from exc
