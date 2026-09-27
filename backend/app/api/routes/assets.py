from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db.session import get_session
from app.models import PriceRecord, Transaction
from app.schemas.assets import AssetCreate, AssetList, AssetRead, AssetUpdate
from app.schemas.prices import PriceRecordList
from app.schemas.transactions import ConversionCreate, ConversionRead, TransactionCreate, TransactionList, TransactionRead, TransactionUpdate
from app.services import assets as asset_service
from app.services import transactions as transaction_service


router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=AssetList)
def list_assets(includeInactive: bool = False, session: Session = Depends(get_session)) -> AssetList:
    items = asset_service.list_assets(session, include_inactive=includeInactive)
    return AssetList(items=items, total=len(items))


@router.post("", response_model=AssetRead, status_code=201)
def create_asset(payload: AssetCreate, session: Session = Depends(get_session)) -> AssetRead:
    return asset_service.create_asset(session, payload)


@router.get("/{asset_id}/prices", response_model=PriceRecordList)
def list_asset_prices(asset_id: str, session: Session = Depends(get_session)) -> PriceRecordList:
    asset = asset_service.get_asset(session, asset_id)
    items = list(
        session.exec(
            select(PriceRecord)
            .where(PriceRecord.assetId == asset_id)
            .order_by(PriceRecord.priceDate.asc(), PriceRecord.createdAt.asc())
        ).all()
    )
    daily_latest_items = _latest_record_per_price_date(items)
    transactions = list(
        session.exec(
            select(Transaction)
            .where(Transaction.assetId == asset_id)
            .order_by(Transaction.transactionDate.asc(), Transaction.createdAt.asc())
        ).all()
    )
    enriched = _with_calculated_daily_income(
        asset.holdingShare,
        asset.entryDate or asset.createdAt.date(),
        daily_latest_items,
        transactions,
    )
    return PriceRecordList(items=list(reversed(enriched)), total=len(enriched))


@router.get("/{asset_id}/transactions", response_model=TransactionList)
def list_asset_transactions(asset_id: str, session: Session = Depends(get_session)) -> TransactionList:
    asset_service.get_asset(session, asset_id)
    items = list(
        session.exec(
            select(Transaction)
            .where(Transaction.assetId == asset_id)
            .order_by(Transaction.transactionDate.desc(), Transaction.createdAt.desc())
        ).all()
    )
    return TransactionList(items=items, total=len(items))


@router.post("/{asset_id}/transactions", response_model=TransactionRead, status_code=201)
def create_asset_transaction(
    asset_id: str,
    payload: TransactionCreate,
    session: Session = Depends(get_session),
) -> TransactionRead:
    return transaction_service.create_transaction(session, asset_id, payload)


@router.patch("/{asset_id}/transactions/{transaction_id}", response_model=TransactionRead)
def update_asset_transaction(
    asset_id: str,
    transaction_id: str,
    payload: TransactionUpdate,
    session: Session = Depends(get_session),
) -> TransactionRead:
    return transaction_service.update_transaction(session, asset_id, transaction_id, payload)


@router.post("/{asset_id}/transactions/convert", response_model=ConversionRead, status_code=201)
def create_asset_conversion(
    asset_id: str,
    payload: ConversionCreate,
    session: Session = Depends(get_session),
) -> ConversionRead:
    out_transaction, in_transaction = transaction_service.create_conversion(session, asset_id, payload)
    return ConversionRead(outTransaction=out_transaction, inTransaction=in_transaction)


@router.get("/{asset_id}", response_model=AssetRead)
def get_asset(asset_id: str, session: Session = Depends(get_session)) -> AssetRead:
    return asset_service.get_asset(session, asset_id)


@router.patch("/{asset_id}", response_model=AssetRead)
def update_asset(asset_id: str, payload: AssetUpdate, session: Session = Depends(get_session)) -> AssetRead:
    return asset_service.update_asset(session, asset_id, payload)


@router.post("/{asset_id}/deactivate", response_model=AssetRead)
def deactivate_asset(asset_id: str, session: Session = Depends(get_session)) -> AssetRead:
    return asset_service.deactivate_asset(session, asset_id)


@router.delete("/{asset_id}")
def delete_asset(asset_id: str, session: Session = Depends(get_session)) -> dict[str, str]:
    asset_service.delete_asset(session, asset_id)
    return {"status": "deleted", "assetId": asset_id}


def _latest_record_per_price_date(items: list[PriceRecord]) -> list[PriceRecord]:
    latest_by_date: dict = {}
    for item in items:
        existing = latest_by_date.get(item.priceDate)
        if not existing:
            latest_by_date[item.priceDate] = item
            continue
        existing_time = existing.fetchedAt or existing.createdAt
        item_time = item.fetchedAt or item.createdAt
        if item_time >= existing_time:
            latest_by_date[item.priceDate] = item
    return [latest_by_date[key] for key in sorted(latest_by_date)]


def _with_calculated_daily_income(
    holding_share: Optional[Decimal],
    entry_date: date,
    items: list[PriceRecord],
    transactions: list[Transaction],
) -> list[dict]:
    # The one-year NAV history seeded at asset creation is useful for price and
    # performance, but income is only meaningful after the asset is recorded.
    # Use the entry-date holding share as the starting position, then replay
    # later transactions so dates before entryDate never get synthetic income.
    valid_price_dates = [item.priceDate for item in items if item.isValid]
    share = _entry_share(holding_share, entry_date, transactions, valid_price_dates)
    previous_valid: Optional[PriceRecord] = None
    transaction_events = _transaction_events(transactions, valid_price_dates)
    transaction_cursor = 0
    enriched: list[dict] = []
    for item in items:
        while transaction_cursor < len(transaction_events) and transaction_events[transaction_cursor][0] <= item.priceDate:
            effective_date, transaction = transaction_events[transaction_cursor]
            if effective_date >= entry_date:
                share = _apply_share_transaction(share, transaction)
            transaction_cursor += 1
        payload = {
            "id": item.id,
            "ownerId": item.ownerId,
            "assetId": item.assetId,
            "productCode": item.productCode,
            "market": item.market,
            "priceDate": item.priceDate,
            "price": item.price,
            "dailyChangePct": item.dailyChangePct,
            "dailyIncomeAmount": item.dailyIncomeAmount,
            "sourceType": item.sourceType,
            "sourceName": item.sourceName,
            "fetchedAt": item.fetchedAt,
            "dataStatus": item.dataStatus,
            "isValid": item.isValid,
            "errorMessage": item.errorMessage,
            "createdAt": item.createdAt,
        }
        if payload["dailyIncomeAmount"] is None and item.isValid and previous_valid and item.priceDate >= entry_date and share > 0:
            payload["dailyIncomeAmount"] = (Decimal(item.price) - Decimal(previous_valid.price)) * share
        if item.isValid:
            previous_valid = item
        enriched.append(payload)
    return enriched


def _entry_share(
    holding_share: Optional[Decimal],
    entry_date: date,
    transactions: list[Transaction],
    valid_price_dates: list[date],
) -> Decimal:
    share = Decimal(str(holding_share or 0))
    for transaction in transactions:
        effective_date = _transaction_effective_date(transaction, valid_price_dates)
        if transaction.transactionDate < entry_date or (effective_date and effective_date < entry_date):
            continue
        transaction_share = Decimal(str(transaction.share or 0))
        if transaction.transactionType in {"buy", "convert_in", "deposit", "contribution", "dca"}:
            share -= transaction_share
        elif transaction.transactionType in {"sell", "convert_out", "withdraw", "redeem"}:
            share += transaction_share
    return max(share, Decimal("0"))


def _transaction_events(transactions: list[Transaction], valid_price_dates: list[date]) -> list[tuple[date, Transaction]]:
    events = []
    for transaction in transactions:
        effective_date = _transaction_effective_date(transaction, valid_price_dates)
        if effective_date:
            events.append((effective_date, transaction))
    return sorted(events, key=lambda item: (item[0], item[1].createdAt))


def _transaction_effective_date(transaction: Transaction, valid_price_dates: list[date]) -> Optional[date]:
    if transaction.transactionType in {"buy", "convert_in", "dca"}:
        return _next_price_date_after(transaction.transactionDate, valid_price_dates)
    return transaction.transactionDate


def _next_price_date_after(transaction_date: date, valid_price_dates: list[date]) -> Optional[date]:
    for price_date in valid_price_dates:
        if price_date > transaction_date:
            return price_date
    return None


def _apply_share_transaction(share: Decimal, transaction: Transaction) -> Decimal:
    transaction_share = Decimal(str(transaction.share or 0))
    if transaction.transactionType in {"buy", "convert_in", "deposit", "contribution", "dca"}:
        return share + transaction_share
    if transaction.transactionType in {"sell", "convert_out", "withdraw", "redeem"}:
        return max(share - transaction_share, Decimal("0"))
    return share
