from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from app.core.config import settings
from app.models import AlertRecord, AlertRule, Asset, DailySnapshot, Setting
from app.services.dashboard import get_dashboard_summary
from app.services.ids import make_id


def generate_alerts(session: Session) -> int:
    rules = {rule.ruleCode: rule for rule in session.exec(select(AlertRule)).all() if rule.isEnabled}
    count = 0
    summary = get_dashboard_summary(session)

    monthly_expense = _setting_decimal(session, "monthly_required_expense")
    if monthly_expense and monthly_expense > 0 and summary.cashCoverageMonths is not None:
        count += _cash_alerts(session, rules, Decimal(summary.cashCoverageMonths))
    count += _equity_ratio_alert(session, rules, Decimal(summary.categorySummary[2].ratio))
    count += _drawdown_alerts(session, rules)

    assets = list(
        session.exec(
            select(Asset).where(
                Asset.ownerId == settings.default_owner_id,
                Asset.assetStatus != "inactive",
            )
        ).all()
    )
    for asset in assets:
        count += _asset_alerts(session, rules, asset)
    session.commit()
    return count


def _cash_alerts(session: Session, rules: dict[str, AlertRule], coverage: Decimal) -> int:
    count = 0
    safety = _setting_decimal(session, "cash_safety_months")
    idle = _setting_decimal(session, "cash_idle_months")
    if safety is not None and coverage < safety:
        count += _create_alert(
            session,
            rules.get("cash_safety"),
            title="现金覆盖月数低于安全线",
            current_value=coverage,
            threshold=safety,
            unit="月",
            reason=f"现金覆盖月数 {coverage:.2f} 低于安全线 {safety} 月。",
        )
    if idle is not None and coverage > idle:
        count += _create_alert(
            session,
            rules.get("cash_idle"),
            title="现金覆盖月数高于闲置线",
            current_value=coverage,
            threshold=idle,
            unit="月",
            reason=f"现金覆盖月数 {coverage:.2f} 高于闲置线 {idle} 月。",
        )
    return count


def _equity_ratio_alert(session: Session, rules: dict[str, AlertRule], equity_ratio: Decimal) -> int:
    threshold = _setting_decimal(session, "equity_ratio_upper_limit")
    if threshold is None or equity_ratio <= threshold:
        return 0
    return _create_alert(
        session,
        rules.get("equity_ratio_high"),
        title="权益仓位高于上限",
        current_value=equity_ratio,
        threshold=threshold,
        unit="%",
        reason=f"权益仓位 {equity_ratio:.2f}% 高于上限 {threshold}%。",
    )


def _drawdown_alerts(session: Session, rules: dict[str, AlertRule]) -> int:
    snapshots = list(
        session.exec(
            select(DailySnapshot)
            .where(DailySnapshot.ownerId == settings.default_owner_id)
            .order_by(DailySnapshot.snapshotDate)
        ).all()
    )
    values = [snapshot.investmentValue for snapshot in snapshots if snapshot.investmentValue is not None]
    if len(values) < 2:
        return 0
    high = max(values)
    current = values[-1]
    if high <= 0:
        return 0
    drawdown = (high - current) / high * Decimal("100")
    strong = _setting_decimal(session, "max_drawdown_strong")
    warning = _setting_decimal(session, "max_drawdown_warning")
    if strong is not None and drawdown > strong:
        return _create_alert(
            session,
            rules.get("portfolio_strong_drawdown"),
            title="投资组合强回撤提醒",
            current_value=drawdown,
            threshold=strong,
            unit="%",
            reason=f"投资组合回撤 {drawdown:.2f}% 高于强风险线 {strong}%。",
        )
    if warning is not None and drawdown > warning:
        return _create_alert(
            session,
            rules.get("portfolio_drawdown"),
            title="投资组合回撤提醒",
            current_value=drawdown,
            threshold=warning,
            unit="%",
            reason=f"投资组合回撤 {drawdown:.2f}% 高于提醒线 {warning}%。",
        )
    return 0


def _asset_alerts(session: Session, rules: dict[str, AlertRule], asset: Asset) -> int:
    count = 0
    today = date.today()
    if asset.assetType == "fixed_income" and asset.maturityDate:
        days = (asset.maturityDate - today).days
        threshold = _setting_decimal(session, "maturity_reminder_days")
        if threshold is not None and 0 <= days <= int(threshold):
            count += _create_alert(
                session,
                rules.get("fixed_income_maturity"),
                title=f"{asset.name} 到期临近",
                current_value=Decimal(days),
                threshold=threshold,
                unit="天",
                reason=f"{asset.name} 距到期日还有 {days} 天。",
                asset=asset,
            )
    if asset.assetType == "debt":
        if asset.repaymentDate:
            days = (asset.repaymentDate - today).days
            threshold = _setting_decimal(session, "repayment_reminder_days")
            if threshold is not None and 0 <= days <= int(threshold):
                count += _create_alert(
                    session,
                    rules.get("debt_repayment"),
                    title=f"{asset.name} 还款临近",
                    current_value=Decimal(days),
                    threshold=threshold,
                    unit="天",
                    reason=f"{asset.name} 距还款日还有 {days} 天。",
                    asset=asset,
                )
        threshold = _setting_decimal(session, "high_interest_debt_rate")
        if threshold is not None and asset.interestRate is not None and asset.interestRate > threshold:
            count += _create_alert(
                session,
                rules.get("high_interest_debt"),
                title=f"{asset.name} 年化利率偏高",
                current_value=asset.interestRate,
                threshold=threshold,
                unit="%",
                reason=f"{asset.name} 年化利率 {asset.interestRate}% 高于 {threshold}%。",
                asset=asset,
            )
    if asset.assetType == "equity":
        delay_days = _setting_decimal(session, "price_delay_days")
        if delay_days is not None and asset.priceDate:
            delayed = (today - asset.priceDate).days
            if delayed > int(delay_days):
                count += _create_alert(
                    session,
                    rules.get("price_data_delay"),
                    title=f"{asset.name} 行情数据延迟",
                    current_value=Decimal(delayed),
                    threshold=delay_days,
                    unit="天",
                    reason=f"{asset.name} 行情日期滞后 {delayed} 天。",
                    asset=asset,
                    price_date=asset.priceDate,
                )
        if asset.dataStatus in {"failed", "abnormal", "missing"}:
            count += _create_alert(
                session,
                rules.get("price_data_abnormal"),
                title=f"{asset.name} 行情数据异常",
                current_value=asset.dataStatus,
                threshold="normal",
                unit=None,
                reason=asset.priceErrorMessage or f"{asset.name} 当前数据状态为 {asset.dataStatus}。",
                asset=asset,
                price_date=asset.priceDate,
            )
    return count


def _create_alert(
    session: Session,
    rule: Optional[AlertRule],
    title: str,
    current_value,
    threshold,
    unit: Optional[str],
    reason: str,
    asset: Optional[Asset] = None,
    price_date: Optional[date] = None,
) -> int:
    if not rule:
        return 0
    existing = session.exec(
        select(AlertRecord).where(
            AlertRecord.ownerId == settings.default_owner_id,
            AlertRecord.ruleCode == rule.ruleCode,
            AlertRecord.targetAssetId == (asset.id if asset else None),
            AlertRecord.status == "pending",
        )
    ).first()
    if existing:
        existing.currentValue = str(current_value)
        existing.thresholdValue = str(threshold)
        existing.reason = reason
        existing.triggeredAt = _now()
        existing.updatedAt = _now()
        existing.priceDate = price_date
        existing.dataSourceType = asset.dataSourceType if asset else None
        existing.dataStatus = asset.dataStatus if asset else None
        session.add(existing)
        return 0
    session.add(
        AlertRecord(
            id=make_id("alert"),
            ownerId=settings.default_owner_id,
            ruleId=rule.id,
            ruleCode=rule.ruleCode,
            alertLevel=rule.alertLevel,
            title=title,
            description=rule.description,
            targetAssetId=asset.id if asset else None,
            targetAssetName=asset.name if asset else None,
            currentValue=str(current_value),
            thresholdValue=str(threshold),
            unit=unit,
            reason=reason,
            status="pending",
            triggeredAt=_now(),
            priceDate=price_date,
            dataSourceType=asset.dataSourceType if asset else None,
            dataStatus=asset.dataStatus if asset else None,
        )
    )
    return 1


def _setting_decimal(session: Session, key: str) -> Optional[Decimal]:
    setting = session.exec(
        select(Setting).where(
            Setting.ownerId == settings.default_owner_id,
            Setting.settingKey == key,
        )
    ).first()
    if not setting:
        return None
    return Decimal(str(setting.settingValue))


def _now() -> datetime:
    return datetime.now(timezone.utc)
