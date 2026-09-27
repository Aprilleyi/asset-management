from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from app.core.config import settings
from app.models import Asset, Setting
from app.schemas.dashboard import CategorySummary, DashboardSummary


def get_dashboard_summary(session: Session) -> DashboardSummary:
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
    counts = {key: 0 for key in values}
    for asset in assets:
        values[asset.assetType] += Decimal(asset.currentValue)
        counts[asset.assetType] += 1

    total_asset = values["cash"] + values["fixed_income"] + values["equity"]
    total_debt = values["debt"]
    net_asset = total_asset - total_debt
    monthly_expense = _get_monthly_expense(session)
    cash_coverage = None
    if monthly_expense and monthly_expense > 0:
        cash_coverage = values["cash"] / monthly_expense

    category_summary = []
    for asset_type in ["cash", "fixed_income", "equity", "debt"]:
        denominator = total_asset if asset_type != "debt" else (total_asset or Decimal("0"))
        ratio = Decimal("0") if denominator == 0 else values[asset_type] / denominator * Decimal("100")
        category_summary.append(
            CategorySummary(
                assetType=asset_type,
                value=values[asset_type],
                ratio=ratio,
                count=counts[asset_type],
            )
        )

    return DashboardSummary(
        totalAsset=total_asset,
        totalDebt=total_debt,
        netAsset=net_asset,
        cashValue=values["cash"],
        fixedIncomeValue=values["fixed_income"],
        equityValue=values["equity"],
        debtValue=values["debt"],
        assetCount=len(assets),
        activeAssetCount=len(assets),
        cashCoverageMonths=cash_coverage,
        dataStatus="missing" if not assets else "normal",
        categorySummary=category_summary,
    )


def _get_monthly_expense(session: Session) -> Optional[Decimal]:
    setting = session.exec(
        select(Setting).where(
            Setting.ownerId == settings.default_owner_id,
            Setting.settingKey == "monthly_required_expense",
        )
    ).first()
    if not setting:
        return None
    return Decimal(str(setting.settingValue))
