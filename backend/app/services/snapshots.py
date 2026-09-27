from datetime import date
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from app.core.config import settings
from app.models import Asset, DailySnapshot


def create_daily_snapshot(session: Session, snapshot_date: Optional[date] = None) -> DailySnapshot:
    target_date = snapshot_date or date.today()
    assets = list(
        session.exec(
            select(Asset).where(
                Asset.ownerId == settings.default_owner_id,
                Asset.assetStatus != "inactive",
            )
        ).all()
    )
    values = {
        "cash": Decimal("0"),
        "fixed_income": Decimal("0"),
        "equity": Decimal("0"),
        "debt": Decimal("0"),
    }
    for asset in assets:
        values[asset.assetType] += Decimal(asset.currentValue)

    total_asset = values["cash"] + values["fixed_income"] + values["equity"]
    total_debt = values["debt"]
    investment_value = values["fixed_income"] + values["equity"]
    snapshot_id = f"snapshot_{target_date.isoformat()}"
    snapshot = session.get(DailySnapshot, snapshot_id)
    payload = {
        "ownerId": settings.default_owner_id,
        "snapshotDate": target_date,
        "totalAsset": total_asset,
        "totalDebt": total_debt,
        "netAsset": total_asset - total_debt,
        "cashValue": values["cash"],
        "fixedIncomeValue": values["fixed_income"],
        "equityValue": values["equity"],
        "debtValue": values["debt"],
        "investmentValue": investment_value,
        "cashRatio": _ratio(values["cash"], total_asset),
        "fixedIncomeRatio": _ratio(values["fixed_income"], total_asset),
        "equityRatio": _ratio(values["equity"], total_asset),
        "debtRatio": _ratio(total_debt, total_asset),
        "portfolioDrawdownPct": _portfolio_drawdown(session, investment_value),
        "dataStatus": "missing" if not assets else "normal",
    }
    if snapshot:
        for key, value in payload.items():
            setattr(snapshot, key, value)
    else:
        snapshot = DailySnapshot(id=snapshot_id, **payload)
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def _ratio(value: Decimal, total: Decimal) -> Decimal:
    if total == 0:
        return Decimal("0")
    return value / total * Decimal("100")


def _portfolio_drawdown(session: Session, investment_value: Decimal) -> Optional[Decimal]:
    snapshots = list(
        session.exec(
            select(DailySnapshot).where(DailySnapshot.ownerId == settings.default_owner_id)
        ).all()
    )
    historical_values = [snapshot.investmentValue for snapshot in snapshots if snapshot.investmentValue is not None]
    if len(historical_values) < 1:
        return None
    high = max(historical_values + [investment_value])
    if high <= 0:
        return None
    return (high - investment_value) / high * Decimal("100")
