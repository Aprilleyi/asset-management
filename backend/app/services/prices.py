import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from app.core.config import settings
from app.core.errors import validation_error
from app.core.messages import PRICE_ERROR_FALLBACK, PRICE_SEED_ERROR_FALLBACK
from app.data_sources.akshare_adapter import AkShareAdapter
from app.data_sources.base import PriceQuote
from app.models import Asset, PriceRecord, TaskLog
from app.schemas.prices import ManualPriceCreate, PriceUpdateRunResult
from app.services.assets import STOCK_ACCOUNT_SUBTYPE, STOCK_HOLDING_SUBTYPES, get_asset
from app.services.ids import make_id


logger = logging.getLogger(__name__)


def update_asset_price(
    session: Session,
    asset_id: str,
    adapter=None,
) -> tuple[Asset, PriceRecord, bool]:
    asset = get_asset(session, asset_id)
    _ensure_equity_asset(asset)
    selected_adapter = adapter or AkShareAdapter()
    try:
        quotes = _fetch_history_for_asset(session, asset, selected_adapter)
        if not quotes:
            quote = _fetch_latest_for_asset(asset, selected_adapter)
            quotes = [quote]
        record: Optional[PriceRecord] = None
        for quote in quotes:
            record = _write_success_record(session, asset, quote)
        _apply_quote_to_asset(asset, quotes[-1])
        session.add(asset)
        session.commit()
        session.refresh(asset)
        if record is None:
            raise RuntimeError(f"No price data for productCode={asset.productCode}")
        session.refresh(record)
        return asset, record, True
    except Exception as exc:
        logger.warning("AKShare price update failed for asset_id=%s product_code=%s", asset.id, asset.productCode, exc_info=True)
        error_message = _friendly_price_error_message()
        record = _write_failed_record(
            session=session,
            asset=asset,
            source_type=selected_adapter.source_type,
            source_name=selected_adapter.source_name,
            error_message=error_message,
        )
        asset.dataSourceType = selected_adapter.source_type
        asset.dataStatus = "failed"
        asset.priceErrorMessage = error_message
        asset.updatedAt = _now()
        session.add(asset)
        session.commit()
        session.refresh(asset)
        session.refresh(record)
        return asset, record, False


def manual_price(session: Session, asset_id: str, payload: ManualPriceCreate) -> tuple[Asset, PriceRecord, bool]:
    asset = get_asset(session, asset_id)
    _ensure_manual_price_asset(asset)
    quote = PriceQuote(
        productCode=_price_record_product_code(asset),
        priceDate=payload.priceDate,
        price=payload.price,
        dailyChangePct=payload.dailyChangePct,
        sourceType="manual",
        sourceName=payload.sourceName,
    )
    record = _write_success_record(session, asset, quote, data_status="manual", daily_income_amount=payload.dailyIncomeAmount)
    _apply_quote_to_asset(asset, quote, data_status="manual", daily_income_amount=payload.dailyIncomeAmount, current_value=payload.currentValue)
    session.add(asset)
    session.commit()
    session.refresh(asset)
    session.refresh(record)
    return asset, record, True


def seed_recent_price_history(session: Session, asset: Asset, adapter=None, limit: Optional[int] = None) -> tuple[int, Optional[PriceRecord], bool]:
    _ensure_equity_asset(asset)
    selected_adapter = adapter or AkShareAdapter()
    history_limit = limit or settings.seed_price_history_days
    try:
        if _is_stock_holding_asset(asset):
            fetch_stock_history = getattr(selected_adapter, "fetch_stock_price_history", None)
            if callable(fetch_stock_history):
                quotes = fetch_stock_history(
                    asset.productCode or "",
                    market=asset.market,
                    start_date=date.today() - timedelta(days=history_limit),
                    end_date=date.today(),
                )
            else:
                quotes = [selected_adapter.fetch_stock_price(asset.productCode or "", market=asset.market)]
        else:
            fetch_history = getattr(selected_adapter, "fetch_price_history", None)
            if callable(fetch_history):
                quotes = fetch_history(
                    asset.productCode or "",
                    start_date=date.today() - timedelta(days=history_limit),
                    end_date=date.today(),
                )
            else:
                quotes = selected_adapter.fetch_recent_prices(asset.productCode or "", limit=history_limit)
        latest_record: Optional[PriceRecord] = None
        for quote in quotes:
            latest_record = _write_success_record(session, asset, quote)
        if quotes:
            _apply_quote_to_asset(asset, quotes[-1])
            session.add(asset)
        session.commit()
        if latest_record:
            session.refresh(latest_record)
        session.refresh(asset)
        return len(quotes), latest_record, True
    except Exception as exc:
        logger.warning("AKShare history seed failed for asset_id=%s product_code=%s", asset.id, asset.productCode, exc_info=True)
        error_message = _friendly_seed_error_message(history_limit)
        record = _write_failed_record(
            session=session,
            asset=asset,
            source_type=selected_adapter.source_type,
            source_name=selected_adapter.source_name,
            error_message=error_message,
        )
        asset.dataSourceType = selected_adapter.source_type
        asset.dataStatus = "failed"
        asset.priceErrorMessage = record.errorMessage
        asset.updatedAt = _now()
        session.add(asset)
        session.commit()
        session.refresh(asset)
        session.refresh(record)
        return 0, record, False


def _fetch_history_for_asset(session: Session, asset: Asset, adapter) -> list[PriceQuote]:
    if _is_stock_holding_asset(asset):
        fetch_stock_history = getattr(adapter, "fetch_stock_price_history", None)
        if callable(fetch_stock_history):
            return fetch_stock_history(
                asset.productCode or "",
                market=asset.market,
                start_date=_price_history_start_date(session, asset),
                end_date=date.today(),
            )
        fetch_stock_price = getattr(adapter, "fetch_stock_price", None)
        if callable(fetch_stock_price):
            return [fetch_stock_price(asset.productCode or "", market=asset.market)]
    fetch_history = getattr(adapter, "fetch_price_history", None)
    if callable(fetch_history):
        return fetch_history(
            asset.productCode or "",
            start_date=_price_history_start_date(session, asset),
            end_date=date.today(),
        )
    fetch_recent = getattr(adapter, "fetch_recent_prices", None)
    if callable(fetch_recent):
        return adapter.fetch_recent_prices(asset.productCode or "", limit=settings.seed_price_history_days)
    return [adapter.fetch_price(asset.productCode or "")]


def _fetch_latest_for_asset(asset: Asset, adapter) -> PriceQuote:
    if _is_stock_holding_asset(asset):
        fetch_stock_price = getattr(adapter, "fetch_stock_price", None)
        if callable(fetch_stock_price):
            return fetch_stock_price(asset.productCode or "", market=asset.market)
    return adapter.fetch_price(asset.productCode or "")


def _price_history_start_date(session: Session, asset: Asset) -> date:
    existing_dates = list(
        session.exec(
            select(PriceRecord.priceDate).where(
                PriceRecord.ownerId == settings.default_owner_id,
                PriceRecord.assetId == asset.id,
                PriceRecord.isValid == True,  # noqa: E712
            )
        ).all()
    )
    candidates = [
        date.today() - timedelta(days=settings.seed_price_history_days),
        asset.createdAt.date() - timedelta(days=14),
    ]
    if asset.priceDate:
        candidates.append(asset.priceDate - timedelta(days=14))
    if existing_dates:
        candidates.append(min(existing_dates))
    return min(candidates)


def run_price_update(session: Session) -> PriceUpdateRunResult:
    started_at = _now()
    task_log = TaskLog(
        id=make_id("tasklog"),
        ownerId=settings.default_owner_id,
        taskType="price_update",
        taskName="手动触发行情更新",
        status="running",
        startedAt=started_at,
    )
    session.add(task_log)
    session.commit()
    session.refresh(task_log)

    assets = list(
        session.exec(
            select(Asset).where(
                Asset.ownerId == settings.default_owner_id,
                Asset.assetType == "equity",
                Asset.assetStatus != "inactive",
                Asset.productCode != None,  # noqa: E711
                Asset.holdingShare != None,  # noqa: E711
            )
        ).all()
    )
    items = []
    success_count = 0
    failed_count = 0
    for asset in assets:
        _, record, success = update_asset_price(session, asset.id)
        success_count += 1 if success else 0
        failed_count += 0 if success else 1
        items.append(
            {
                "assetId": asset.id,
                "productCode": asset.productCode,
                "success": success,
                "priceRecord": record,
            }
        )

    task_log.status = _task_status(success_count, failed_count)
    task_log.finishedAt = _now()
    task_log.durationMs = int((task_log.finishedAt - started_at).total_seconds() * 1000)
    task_log.successCount = success_count
    task_log.failedCount = failed_count
    task_log.skippedCount = 0
    task_log.message = f"行情更新完成：成功 {success_count}，失败 {failed_count}"
    session.add(task_log)
    session.commit()
    session.refresh(task_log)
    return PriceUpdateRunResult(
        taskLogId=task_log.id,
        status=task_log.status,
        successCount=success_count,
        failedCount=failed_count,
        items=items,
    )


def _ensure_equity_asset(asset: Asset) -> None:
    if asset.assetType != "equity":
        raise validation_error("Only equity assets support price updates")
    if _is_stock_account_asset(asset):
        raise validation_error("Stock account assets do not support direct price updates")
    if not asset.productCode:
        raise validation_error("Equity asset productCode is required for price updates")
    if asset.holdingShare is None or Decimal(asset.holdingShare) <= 0:
        raise validation_error("Equity asset holdingShare is required for price updates")


def _ensure_manual_price_asset(asset: Asset) -> None:
    if asset.assetType not in {"cash", "equity", "fixed_income"}:
        raise validation_error("Only cash, equity, and fixed income assets support manual price records")
    if asset.assetType == "equity":
        _ensure_equity_asset(asset)


def _price_record_product_code(asset: Asset) -> str:
    return asset.productCode or asset.id


def _is_stock_holding_asset(asset: Asset) -> bool:
    return asset.assetType == "equity" and asset.subType in STOCK_HOLDING_SUBTYPES


def _is_stock_account_asset(asset: Asset) -> bool:
    return asset.assetType == "equity" and asset.subType == STOCK_ACCOUNT_SUBTYPE


def _write_success_record(
    session: Session,
    asset: Asset,
    quote: PriceQuote,
    data_status: str = "normal",
    daily_income_amount: Optional[Decimal] = None,
) -> PriceRecord:
    if daily_income_amount is None:
        daily_income_amount = _calculate_daily_income_amount(session, asset, quote)
    record = session.exec(
        select(PriceRecord).where(
            PriceRecord.ownerId == settings.default_owner_id,
            PriceRecord.assetId == asset.id,
            PriceRecord.priceDate == quote.priceDate,
            PriceRecord.sourceType == quote.sourceType,
        )
    ).first()
    if not record:
        record = PriceRecord(
            id=make_id("price"),
            ownerId=settings.default_owner_id,
            assetId=asset.id,
            productCode=quote.productCode,
            market=asset.market,
            priceDate=quote.priceDate,
            price=quote.price,
            sourceType=quote.sourceType,
            fetchedAt=_now(),
            dataStatus=data_status,
        )
    record.productCode = quote.productCode
    record.market = asset.market
    record.price = quote.price
    record.dailyChangePct = quote.dailyChangePct
    record.dailyIncomeAmount = daily_income_amount
    record.sourceName = quote.sourceName
    record.fetchedAt = _now()
    record.dataStatus = data_status
    record.isValid = True
    record.errorMessage = None
    session.add(record)
    session.flush()
    return record


def _write_failed_record(
    session: Session,
    asset: Asset,
    source_type: str,
    source_name: str,
    error_message: str,
) -> PriceRecord:
    record = PriceRecord(
        id=make_id("price"),
        ownerId=settings.default_owner_id,
        assetId=asset.id,
        productCode=asset.productCode or "",
        market=asset.market,
        priceDate=asset.priceDate or date.today(),
        price=asset.latestPrice or Decimal("0"),
        dailyChangePct=asset.dailyChangePct,
        dailyIncomeAmount=asset.dailyIncomeAmount,
        sourceType=source_type,
        sourceName=source_name,
        fetchedAt=_now(),
        dataStatus="failed",
        isValid=False,
        errorMessage=error_message,
    )
    session.add(record)
    session.flush()
    return record


def _apply_quote_to_asset(
    asset: Asset,
    quote: PriceQuote,
    data_status: str = "normal",
    daily_income_amount: Optional[Decimal] = None,
    current_value: Optional[Decimal] = None,
) -> None:
    asset.latestPrice = quote.price
    if asset.assetType == "cash":
        asset.expectedReturnRate = quote.price
    asset.priceDate = quote.priceDate
    asset.dailyChangePct = quote.dailyChangePct
    asset.dailyIncomeAmount = daily_income_amount
    asset.dataSourceType = quote.sourceType
    asset.dataStatus = data_status
    asset.priceErrorMessage = None
    share = Decimal(asset.holdingShare or 0)
    if current_value is not None:
        asset.currentValue = current_value
    elif share > 0:
        asset.currentValue = share * quote.price
    _refresh_asset_gain_fields(asset)
    asset.updatedAt = _now()


def _calculate_daily_income_amount(session: Session, asset: Asset, quote: PriceQuote) -> Optional[Decimal]:
    entry_date = asset.entryDate or asset.createdAt.date()
    share = Decimal(asset.holdingShare or 0)
    if quote.priceDate < entry_date or share <= 0:
        return None
    previous = session.exec(
        select(PriceRecord)
        .where(
            PriceRecord.ownerId == settings.default_owner_id,
            PriceRecord.assetId == asset.id,
            PriceRecord.isValid == True,  # noqa: E712
            PriceRecord.priceDate < quote.priceDate,
        )
        .order_by(PriceRecord.priceDate.desc(), PriceRecord.fetchedAt.desc())
    ).first()
    if not previous:
        return None
    return (quote.price - Decimal(previous.price)) * share


def _refresh_asset_gain_fields(asset: Asset) -> None:
    current_value = Decimal(asset.currentValue or 0)
    holding_cost = _holding_cost_basis(asset)
    if holding_cost is not None:
        asset.holdingGain = current_value - holding_cost
    if asset.cumulativeNetBasis is not None:
        asset.cumulativeGain = current_value - Decimal(asset.cumulativeNetBasis)


def _holding_cost_basis(asset: Asset) -> Optional[Decimal]:
    share = Decimal(asset.holdingShare or 0)
    if asset.holdingCostPrice is not None and share > 0:
        return Decimal(asset.holdingCostPrice) * share
    if asset.costAmount is not None:
        return Decimal(asset.costAmount)
    if asset.principalAmount is not None:
        return Decimal(asset.principalAmount)
    return None


def _task_status(success_count: int, failed_count: int) -> str:
    if failed_count == 0:
        return "success"
    if success_count > 0:
        return "partial_success"
    return "failed"


def _friendly_price_error_message() -> str:
    return PRICE_ERROR_FALLBACK


def _friendly_seed_error_message(history_limit: int) -> str:
    return PRICE_SEED_ERROR_FALLBACK.format(days=history_limit)


def _now() -> datetime:
    return datetime.now(timezone.utc)
