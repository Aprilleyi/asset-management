from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from app.core.config import settings
from app.core.errors import not_found, validation_error
from app.models import AlertRecord, Asset, PriceRecord, Transaction
from app.schemas.assets import AssetCreate, AssetUpdate
from app.services.ids import make_id

STOCK_HOLDING_SUBTYPES = {"A股股票", "港股股票", "美股股票"}
STOCK_ACCOUNT_SUBTYPE = "股票账户"


def list_assets(session: Session, include_inactive: bool = False) -> list[Asset]:
    statement = select(Asset).where(Asset.ownerId == settings.default_owner_id)
    if not include_inactive:
        statement = statement.where(Asset.assetStatus != "inactive")
    return list(session.exec(statement.order_by(Asset.createdAt.desc())).all())


def get_asset(session: Session, asset_id: str) -> Asset:
    asset = session.get(Asset, asset_id)
    if not asset or asset.ownerId != settings.default_owner_id:
        raise not_found("Asset not found")
    return asset


def create_asset(session: Session, payload: AssetCreate) -> Asset:
    current_value_provided = "currentValue" in payload.model_fields_set
    explicit_fields = set(payload.model_fields_set)
    data = payload.model_dump()
    data["entryDate"] = data.get("entryDate") or date.today()
    _validate_asset_payload(data, is_create=True)
    _apply_share_price_current_value(data, force=not current_value_provided)
    _apply_holding_cost_from_gain(data, explicit_fields)
    _apply_holding_gain_from_cost(data)
    _apply_cumulative_basis_from_gain(data, explicit_fields)
    _ensure_default_cumulative_basis(data)
    _ensure_dca_next_date(data)
    _refresh_gain_fields(data)

    asset = Asset(
        id=make_id("asset"),
        ownerId=settings.default_owner_id,
        **data,
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    if settings.seed_price_history_on_create and asset.assetType == "equity" and asset.productCode and asset.holdingShare:
        from app.services.prices import seed_recent_price_history

        seed_recent_price_history(session, asset, limit=settings.seed_price_history_days)
        session.refresh(asset)
    return asset


def update_asset(session: Session, asset_id: str, payload: AssetUpdate) -> Asset:
    asset = get_asset(session, asset_id)
    data = payload.model_dump(exclude_unset=True)
    merged = {**asset.model_dump(), **data}
    _validate_asset_payload(merged, is_create=False)
    _apply_share_price_current_value(merged, force="currentValue" not in data)
    inferred_fields = _apply_holding_cost_from_gain(merged, set(data.keys()))
    inferred_fields.update(_apply_holding_gain_from_cost(merged))
    inferred_fields.update(_apply_cumulative_basis_from_gain(merged, set(data.keys())))
    inferred_fields.update(_ensure_default_cumulative_basis(merged))
    inferred_fields.update(_ensure_dca_next_date(merged))
    _refresh_gain_fields(merged)

    for key, value in data.items():
        setattr(asset, key, merged[key])
    for key in inferred_fields:
        setattr(asset, key, merged[key])
    if {"currentValue", "holdingShare", "holdingCostPrice", "costAmount", "cumulativeNetBasis"} & (set(data.keys()) | inferred_fields):
        asset.holdingGain = merged.get("holdingGain")
        asset.cumulativeGain = merged.get("cumulativeGain")
    if "holdingShare" in data or "latestPrice" in data or "assetType" in data:
        asset.currentValue = merged["currentValue"]
    asset.updatedAt = _now()
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def deactivate_asset(session: Session, asset_id: str) -> Asset:
    asset = get_asset(session, asset_id)
    asset.assetStatus = "inactive"
    asset.updatedAt = _now()
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def delete_asset(session: Session, asset_id: str) -> None:
    asset = get_asset(session, asset_id)
    related_transactions = list(
        session.exec(
            select(Transaction).where(
                Transaction.ownerId == settings.default_owner_id,
                (Transaction.assetId == asset_id) | (Transaction.relatedAssetId == asset_id),
            )
        ).all()
    )
    related_prices = list(
        session.exec(
            select(PriceRecord).where(
                PriceRecord.ownerId == settings.default_owner_id,
                PriceRecord.assetId == asset_id,
            )
        ).all()
    )
    related_alerts = list(
        session.exec(
            select(AlertRecord).where(
                AlertRecord.ownerId == settings.default_owner_id,
                AlertRecord.targetAssetId == asset_id,
            )
        ).all()
    )
    for item in [*related_transactions, *related_prices, *related_alerts]:
        session.delete(item)
    session.delete(asset)
    session.commit()


def _validate_asset_payload(data: dict, is_create: bool) -> None:
    name = data.get("name")
    platform = data.get("platform")
    asset_type = data.get("assetType")

    if not name or not str(name).strip():
        raise validation_error("Asset name is required")
    if not platform or not str(platform).strip():
        raise validation_error("Asset platform is required")
    if asset_type not in {"cash", "fixed_income", "equity", "debt"}:
        raise validation_error("assetType must be one of cash, fixed_income, equity, debt")
    if data.get("assetStatus", "active") not in {"active", "inactive", "closed"}:
        raise validation_error("assetStatus must be one of active, inactive, closed")
    _require_non_negative(data, "currentValue")

    if asset_type == "cash":
        _require_non_negative(data, "expectedReturnRate", required=False)
        _require_non_negative(data, "latestPrice", required=False)
    elif asset_type == "fixed_income":
        _require_non_negative(data, "costAmount", required=False)
        _require_non_negative(data, "principalAmount", required=False)
        _require_non_negative(data, "expectedReturnRate", required=False)
        _require_non_negative(data, "holdingCostPrice", required=False)
        _require_non_negative(data, "latestPrice", required=False)
        if data.get("holdingShare") is not None and Decimal(str(data["holdingShare"])) <= 0:
            raise validation_error("holdingShare must be greater than 0 when provided")
    elif asset_type == "equity":
        stock_account = _is_stock_account_asset(data)
        stock_holding = _is_stock_holding_asset(data)
        if data.get("isDca") and (stock_account or stock_holding):
            raise validation_error("DCA is only supported for fund-like equity assets")
        if is_create and not stock_account and data.get("holdingShare") is None:
            raise validation_error("holdingShare is required for equity assets except stock account")
        if data.get("holdingShare") is not None and Decimal(str(data["holdingShare"])) <= 0:
            raise validation_error("holdingShare must be greater than 0 for equity assets")
        _require_non_negative(data, "costAmount", required=False)
        _require_non_negative(data, "holdingCostPrice", required=False)
        _require_non_negative(data, "latestPrice", required=False)
        if data.get("isDca"):
            if data.get("dcaAmount") is None or Decimal(str(data["dcaAmount"])) <= 0:
                raise validation_error("dcaAmount must be greater than 0 when isDca is true")
            if data.get("dcaFrequency") not in {"daily", "weekly", "biweekly", "monthly"}:
                raise validation_error("dcaFrequency must be one of daily, weekly, biweekly, monthly")
            if data.get("dcaFrequency") in {"weekly", "biweekly", "monthly"} and not data.get("dcaDay"):
                raise validation_error("dcaDay is required for weekly, biweekly, and monthly DCA")
    elif asset_type == "debt":
        _require_non_negative(data, "interestRate", required=False)


def _require_non_negative(data: dict, field: str, required: bool = True) -> None:
    value = data.get(field)
    if value is None:
        if required:
            raise validation_error(f"{field} is required")
        return
    if Decimal(str(value)) < 0:
        raise validation_error(f"{field} must be greater than or equal to 0")


def _is_stock_holding_asset(data: dict) -> bool:
    return data.get("assetType") == "equity" and data.get("subType") in STOCK_HOLDING_SUBTYPES


def _is_stock_account_asset(data: dict) -> bool:
    return data.get("assetType") == "equity" and data.get("subType") == STOCK_ACCOUNT_SUBTYPE


def _apply_share_price_current_value(data: dict, force: bool = False) -> None:
    if data.get("assetType") not in {"equity", "fixed_income"}:
        return
    if force and data.get("holdingShare") is not None and data.get("latestPrice") is not None:
        data["currentValue"] = Decimal(str(data["holdingShare"])) * Decimal(str(data["latestPrice"]))


def _apply_holding_cost_from_gain(data: dict, explicit_fields: set[str]) -> set[str]:
    if data.get("assetType") not in {"equity", "fixed_income"} or "holdingGain" not in explicit_fields:
        return set()
    if data.get("holdingGain") is None or data.get("currentValue") is None:
        return set()

    current_value = Decimal(str(data["currentValue"]))
    holding_gain = Decimal(str(data["holdingGain"]))
    holding_cost = current_value - holding_gain
    if holding_cost < 0:
        raise validation_error("holdingGain cannot be greater than currentValue")

    inferred_fields: set[str] = set()
    if "costAmount" not in explicit_fields and data.get("costAmount") is None:
        data["costAmount"] = holding_cost
        inferred_fields.add("costAmount")

    share = Decimal(str(data.get("holdingShare") or 0))
    if "holdingCostPrice" not in explicit_fields and data.get("holdingCostPrice") is None and share > 0:
        data["holdingCostPrice"] = holding_cost / share
        inferred_fields.add("holdingCostPrice")
    return inferred_fields


def _apply_holding_gain_from_cost(data: dict) -> set[str]:
    if data.get("assetType") not in {"equity", "fixed_income"} or data.get("currentValue") is None:
        return set()
    holding_cost = _holding_cost_basis(data)
    if holding_cost is None:
        return set()
    data["holdingGain"] = Decimal(str(data["currentValue"])) - holding_cost
    return {"holdingGain"}


def _apply_cumulative_basis_from_gain(data: dict, explicit_fields: set[str]) -> set[str]:
    if data.get("assetType") not in {"equity", "fixed_income"} or "cumulativeGain" not in explicit_fields:
        return set()
    if data.get("cumulativeGain") is None or data.get("currentValue") is None:
        return set()

    current_value = Decimal(str(data["currentValue"]))
    cumulative_gain = Decimal(str(data["cumulativeGain"]))
    data["cumulativeNetBasis"] = current_value - cumulative_gain
    return {"cumulativeNetBasis"}


def _ensure_default_cumulative_basis(data: dict) -> set[str]:
    if data.get("assetType") not in {"equity", "fixed_income"} or data.get("cumulativeNetBasis") is not None:
        return set()
    if data.get("costAmount") is None:
        return set()
    data["cumulativeNetBasis"] = Decimal(str(data["costAmount"]))
    return {"cumulativeNetBasis"}


def _refresh_gain_fields(data: dict) -> None:
    if data.get("assetType") not in {"equity", "fixed_income"} or data.get("currentValue") is None:
        return

    current_value = Decimal(str(data["currentValue"]))
    holding_cost = _holding_cost_basis(data)
    if holding_cost is not None:
        data["holdingGain"] = current_value - holding_cost

    cumulative_basis = data.get("cumulativeNetBasis")
    if cumulative_basis is not None:
        data["cumulativeGain"] = current_value - Decimal(str(cumulative_basis))


def _holding_cost_basis(data: dict) -> Optional[Decimal]:
    share = Decimal(str(data.get("holdingShare") or 0))
    if data.get("holdingCostPrice") is not None and share > 0:
        return Decimal(str(data["holdingCostPrice"])) * share
    if data.get("costAmount") is not None:
        return Decimal(str(data["costAmount"]))
    if data.get("principalAmount") is not None:
        return Decimal(str(data["principalAmount"]))
    return None


def _ensure_dca_next_date(data: dict) -> set[str]:
    if not data.get("isDca") or data.get("dcaNextDate") is not None:
        return set()
    data["dcaNextDate"] = _next_dca_date_on_or_after(date.today(), data.get("dcaFrequency"), data.get("dcaDay"))
    return {"dcaNextDate"}


def _next_dca_date_on_or_after(base_date: date, frequency: Optional[str], dca_day: Optional[str]) -> date:
    if frequency in {"weekly", "biweekly"}:
        target_weekday = max(1, min(int(dca_day or 1), 7))
        return base_date + timedelta(days=(target_weekday - base_date.isoweekday()) % 7)
    if frequency == "monthly":
        target_day = max(1, min(int(dca_day or 1), 28))
        candidate = base_date.replace(day=target_day)
        if candidate < base_date:
            return _add_month(candidate, 1)
        return candidate
    return base_date


def _add_month(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month)


def _now() -> datetime:
    return datetime.now(timezone.utc)
