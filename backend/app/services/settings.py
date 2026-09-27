from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlmodel import Session, select

from app.core.config import settings as app_settings
from app.core.errors import not_found, validation_error
from app.models import Setting


NON_NEGATIVE_NUMBER_SETTINGS = {
    "monthly_required_expense",
    "cash_safety_months",
    "cash_idle_months",
    "equity_ratio_upper_limit",
    "max_drawdown_warning",
    "max_drawdown_strong",
    "maturity_reminder_days",
    "repayment_reminder_days",
    "high_interest_debt_rate",
    "price_delay_days",
    "backup_retention_days",
}


def list_settings(session: Session) -> list[Setting]:
    statement = select(Setting).where(Setting.ownerId == app_settings.default_owner_id)
    return list(session.exec(statement.order_by(Setting.category, Setting.settingKey)).all())


def update_setting(session: Session, setting_key: str, setting_value: str) -> Setting:
    setting = _get_setting_by_key(session, setting_key)
    if not setting.isEditable:
        raise validation_error("Setting is not editable")
    _validate_setting_value(setting, setting_value)
    setting.settingValue = setting_value
    setting.updatedAt = datetime.now(timezone.utc)
    session.add(setting)
    session.commit()
    session.refresh(setting)
    return setting


def _get_setting_by_key(session: Session, setting_key: str) -> Setting:
    statement = select(Setting).where(
        Setting.ownerId == app_settings.default_owner_id,
        Setting.settingKey == setting_key,
    )
    setting = session.exec(statement).first()
    if not setting:
        raise not_found("Setting not found")
    return setting


def _validate_setting_value(setting: Setting, value: str) -> None:
    if value == "":
        raise validation_error("settingValue cannot be empty")
    if setting.valueType == "number":
        try:
            parsed = Decimal(str(value))
        except InvalidOperation as exc:
            raise validation_error("settingValue must be a valid number") from exc
        if setting.settingKey in NON_NEGATIVE_NUMBER_SETTINGS and parsed < 0:
            raise validation_error("settingValue must be greater than or equal to 0")
    elif setting.valueType == "boolean" and str(value).lower() not in {"true", "false"}:
        raise validation_error("settingValue must be true or false")
