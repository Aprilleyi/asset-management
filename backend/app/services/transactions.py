from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Union

from sqlmodel import Session, select

from app.core.config import settings
from app.data_sources.akshare_adapter import AkShareAdapter
from app.core.errors import not_found, validation_error
from app.models import Asset, Transaction
from app.schemas.transactions import ConversionCreate, TransactionCreate, TransactionUpdate
from app.services import assets as asset_service
from app.services.ids import make_id


def create_transaction(session: Session, asset_id: str, payload: TransactionCreate) -> Transaction:
    asset = asset_service.get_asset(session, asset_id)
    data = payload.model_dump()
    _complete_transaction_from_price(asset, data)
    transaction = Transaction(
        id=make_id("transaction"),
        ownerId=settings.default_owner_id,
        assetId=asset.id,
        **data,
    )
    _apply_transaction_to_asset(asset, transaction)
    session.add(transaction)
    session.add(asset)
    session.commit()
    session.refresh(transaction)
    return transaction


def generate_due_dca_transactions(session: Session, today: Optional[date] = None) -> int:
    run_date = today or date.today()
    assets = list(
        session.exec(
            select(Asset).where(
                Asset.ownerId == settings.default_owner_id,
                Asset.assetType == "equity",
                Asset.assetStatus != "inactive",
                Asset.isDca == True,  # noqa: E712
            )
        ).all()
    )
    generated_count = 0
    for asset in assets:
        if not asset.dcaAmount or asset.dcaAmount <= 0:
            continue
        next_date = asset.dcaNextDate or _next_dca_date_on_or_after(run_date, asset.dcaFrequency, asset.dcaDay)
        guard = 0
        while next_date and next_date <= run_date and guard < 120:
            guard += 1
            if not _dca_transaction_exists(session, asset.id, next_date):
                try:
                    transaction = _create_dca_transaction(asset, next_date)
                except Exception as exc:
                    asset.dcaStatus = f"failed: {str(exc)[:200]}"
                    break
                _apply_transaction_to_asset(asset, transaction)
                session.add(transaction)
                generated_count += 1
            next_date = _next_dca_date_after(next_date, asset.dcaFrequency, asset.dcaDay)
        asset.dcaNextDate = next_date
        if generated_count:
            asset.dcaStatus = "active"
        asset.updatedAt = _now()
        session.add(asset)
    session.commit()
    return generated_count


def create_conversion(session: Session, asset_id: str, payload: ConversionCreate) -> tuple[Transaction, Transaction]:
    source_asset = asset_service.get_asset(session, asset_id)
    target_asset = asset_service.get_asset(session, payload.targetAssetId)
    if source_asset.id == target_asset.id:
        raise validation_error("targetAssetId must be different from source asset")

    in_amount = payload.inAmount
    if in_amount is None:
        in_amount = payload.outAmount - (payload.feeAmount or Decimal("0"))
    if in_amount <= 0:
        raise validation_error("inAmount must be greater than 0 after fees")

    out_transaction_id = make_id("transaction")
    in_transaction_id = make_id("transaction")
    out_transaction = Transaction(
        id=out_transaction_id,
        ownerId=settings.default_owner_id,
        assetId=source_asset.id,
        relatedAssetId=target_asset.id,
        relatedTransactionId=in_transaction_id,
        transactionType="convert_out",
        amount=payload.outAmount,
        share=payload.outShare,
        price=payload.outPrice,
        feeAmount=payload.feeAmount,
        feeRate=payload.feeRate,
        tradeTiming=payload.tradeTiming,
        transactionDate=payload.transactionDate,
        source=payload.source,
        note=payload.note,
    )
    in_transaction = Transaction(
        id=in_transaction_id,
        ownerId=settings.default_owner_id,
        assetId=target_asset.id,
        relatedAssetId=source_asset.id,
        relatedTransactionId=out_transaction_id,
        transactionType="convert_in",
        amount=in_amount,
        share=payload.inShare,
        price=payload.inPrice,
        feeAmount=None,
        feeRate=None,
        tradeTiming=payload.tradeTiming,
        transactionDate=payload.transactionDate,
        source=payload.source,
        note=payload.note,
    )

    _apply_transaction_to_asset(source_asset, out_transaction)
    _apply_transaction_to_asset(target_asset, in_transaction)
    session.add(out_transaction)
    session.add(in_transaction)
    session.add(source_asset)
    session.add(target_asset)
    session.commit()
    session.refresh(out_transaction)
    session.refresh(in_transaction)
    return out_transaction, in_transaction


def update_transaction(session: Session, asset_id: str, transaction_id: str, payload: TransactionUpdate) -> Transaction:
    asset = asset_service.get_asset(session, asset_id)
    transaction = session.get(Transaction, transaction_id)
    if not transaction or transaction.assetId != asset.id or transaction.ownerId != settings.default_owner_id:
        raise not_found("Transaction not found")
    if transaction.transactionType != "dca":
        raise validation_error("Only dca transaction amount can be edited")
    if payload.amount is None:
        return transaction

    old_amount = _decimal(transaction.amount)
    old_fee = _decimal(transaction.feeAmount)
    old_share = _decimal(transaction.share)
    price = _decimal(transaction.price)
    if price <= 0:
        raise validation_error("DCA transaction price is required to recalculate share")

    new_amount = _decimal(payload.amount)
    fee = _effective_fee(new_amount, None, transaction.feeRate)
    net_amount = new_amount - fee
    if net_amount <= 0:
        raise validation_error("amount must be greater than fee")
    new_share = net_amount / price

    _apply_dca_delta_to_asset(asset, old_amount + old_fee, old_share, new_amount + fee, new_share)
    transaction.amount = new_amount
    transaction.feeAmount = fee
    transaction.share = new_share
    transaction.updatedAt = _now()
    session.add(asset)
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    return transaction


def _complete_transaction_from_price(asset: Asset, data: dict) -> None:
    if asset.assetType != "equity" or data.get("transactionType") not in {"buy", "sell", "dca"}:
        return
    if data.get("price") is not None and data.get("share") is not None:
        data["feeAmount"] = _effective_fee(_decimal(data.get("amount")), data.get("feeAmount"), data.get("feeRate"))
        return
    quote = _confirmation_quote(asset, data["transactionDate"], data.get("tradeTiming", "before_15"))
    data["price"] = quote.price
    data["transactionDate"] = quote.priceDate
    if data["transactionType"] in {"buy", "dca"}:
        if data.get("amount") is None and data.get("share") is not None:
            data["amount"] = _decimal(data.get("share")) * quote.price
        fee = _effective_fee(_decimal(data.get("amount")), data.get("feeAmount"), data.get("feeRate"))
        data["feeAmount"] = fee
        if data.get("share") is None:
            net_amount = _decimal(data.get("amount")) - fee
            if net_amount <= 0:
                raise validation_error("buy amount must be greater than fee")
            data["share"] = net_amount / quote.price
    elif data["transactionType"] == "sell":
        if data.get("share") is None and data.get("amount") is not None:
            data["share"] = _decimal(data.get("amount")) / quote.price
        share = _decimal(data.get("share"))
        if share <= 0:
            raise validation_error("share or amount is required for sell transactions")
        if data.get("amount") is None:
            data["amount"] = share * quote.price
        data["feeAmount"] = _effective_fee(data["amount"], data.get("feeAmount"), data.get("feeRate"))


def _confirmation_quote(asset: Asset, requested_date: date, trade_timing: str):
    if not asset.productCode:
        raise validation_error("productCode is required to calculate transaction price")
    start_date = requested_date - timedelta(days=7)
    end_date = requested_date + timedelta(days=14)
    try:
        quotes = AkShareAdapter().fetch_price_history(asset.productCode, start_date=start_date, end_date=end_date)
    except Exception as exc:
        raise validation_error(f"AKShare price lookup failed: {exc}") from exc
    quote_dates = [quote for quote in quotes if quote.priceDate >= requested_date]
    if trade_timing == "after_15":
        quote_dates = [quote for quote in quotes if quote.priceDate > requested_date]
    if not quote_dates:
        raise validation_error("No confirmation price found for transaction date")
    return quote_dates[0]


def _effective_fee(amount: Decimal, fee_amount: Optional[Decimal], fee_rate: Optional[Decimal]) -> Decimal:
    if fee_amount is not None:
        return _decimal(fee_amount)
    if fee_rate is not None:
        return amount * _decimal(fee_rate) / Decimal("100")
    return Decimal("0")


def _apply_transaction_to_asset(asset: Asset, transaction: Transaction) -> None:
    amount = transaction.amount or Decimal("0")
    fee = transaction.feeAmount or Decimal("0")
    share = transaction.share or Decimal("0")
    if transaction.transactionType in {"buy", "convert_in", "dca"}:
        _increase_asset(asset, amount, share)
    elif transaction.transactionType in {"sell", "convert_out"}:
        _decrease_asset(asset, amount, share)
    elif transaction.transactionType == "cash_dividend":
        _decrease_cumulative_basis(asset, amount)
    else:
        raise validation_error("Unsupported transactionType")
    if fee > 0 and transaction.transactionType in {"buy", "convert_in", "dca"}:
        asset.costAmount = _decimal(asset.costAmount) + fee
        _increase_cumulative_basis(asset, fee)
    _refresh_gain_fields(asset)
    asset.updatedAt = _now()


def _increase_asset(asset: Asset, amount: Decimal, share: Decimal) -> None:
    asset.costAmount = _decimal(asset.costAmount) + amount
    _increase_cumulative_basis(asset, amount)
    if share > 0:
        asset.holdingShare = _decimal(asset.holdingShare) + share
    _refresh_holding_cost_price(asset)
    _refresh_current_value_after_share_change(asset, amount_delta=amount)


def _decrease_asset(asset: Asset, amount: Decimal, share: Decimal) -> None:
    if share > 0:
        current_share = _decimal(asset.holdingShare)
        if current_share and share > current_share:
            raise validation_error("share cannot be greater than current holdingShare")
        asset.holdingShare = max(current_share - share, Decimal("0"))
    if asset.assetType in {"cash", "fixed_income", "debt"}:
        asset.currentValue = max(_decimal(asset.currentValue) - amount, Decimal("0"))
    else:
        _decrease_cumulative_basis(asset, amount)
        _refresh_current_value_after_share_change(asset, amount_delta=-amount)


def _refresh_current_value_after_share_change(asset: Asset, amount_delta: Decimal) -> None:
    asset.currentValue = max(_decimal(asset.currentValue) + amount_delta, Decimal("0"))


def _refresh_holding_cost_price(asset: Asset) -> None:
    if asset.holdingCostPrice is not None:
        return
    share = _decimal(asset.holdingShare)
    if share > 0 and asset.costAmount is not None:
        asset.holdingCostPrice = _decimal(asset.costAmount) / share


def _increase_cumulative_basis(asset: Asset, amount: Decimal) -> None:
    asset.cumulativeNetBasis = _decimal(asset.cumulativeNetBasis) + amount


def _decrease_cumulative_basis(asset: Asset, amount: Decimal) -> None:
    asset.cumulativeNetBasis = max(_decimal(asset.cumulativeNetBasis) - amount, Decimal("0"))


def _refresh_gain_fields(asset: Asset) -> None:
    current_value = _decimal(asset.currentValue)
    holding_cost = _holding_cost_basis(asset)
    if holding_cost is not None:
        asset.holdingGain = current_value - holding_cost
    if asset.cumulativeNetBasis is not None:
        asset.cumulativeGain = current_value - _decimal(asset.cumulativeNetBasis)


def _holding_cost_basis(asset: Asset) -> Optional[Decimal]:
    share = _decimal(asset.holdingShare)
    if asset.holdingCostPrice is not None and share > 0:
        return _decimal(asset.holdingCostPrice) * share
    if asset.costAmount is not None:
        return _decimal(asset.costAmount)
    if asset.principalAmount is not None:
        return _decimal(asset.principalAmount)
    return None


def _apply_dca_delta_to_asset(asset: Asset, old_total_amount: Decimal, old_share: Decimal, new_total_amount: Decimal, new_share: Decimal) -> None:
    amount_delta = new_total_amount - old_total_amount
    share_delta = new_share - old_share
    asset.costAmount = _decimal(asset.costAmount) + amount_delta
    asset.cumulativeNetBasis = _decimal(asset.cumulativeNetBasis) + amount_delta
    asset.holdingShare = max(_decimal(asset.holdingShare) + share_delta, Decimal("0"))
    _refresh_current_value_after_share_change(asset, amount_delta=amount_delta)
    _refresh_gain_fields(asset)
    asset.updatedAt = _now()


def _create_dca_transaction(asset: Asset, scheduled_date: date) -> Transaction:
    data = {
        "transactionType": "dca",
        "amount": asset.dcaAmount,
        "share": None,
        "price": None,
        "feeAmount": None,
        "feeRate": None,
        "tradeTiming": "before_15",
        "transactionDate": scheduled_date,
        "source": "system_dca",
        "note": _dca_note(scheduled_date),
    }
    try:
        _complete_transaction_from_price(asset, data)
    except Exception:
        if asset.latestPrice is None:
            raise
        price = _decimal(asset.latestPrice)
        data["price"] = price
        data["share"] = _decimal(data["amount"]) / price
    return Transaction(
        id=make_id("transaction"),
        ownerId=settings.default_owner_id,
        assetId=asset.id,
        **data,
    )


def _dca_transaction_exists(session: Session, asset_id: str, scheduled_date: date) -> bool:
    existing = session.exec(
        select(Transaction).where(
            Transaction.ownerId == settings.default_owner_id,
            Transaction.assetId == asset_id,
            Transaction.source == "system_dca",
            Transaction.note == _dca_note(scheduled_date),
        )
    ).first()
    return existing is not None


def _dca_note(scheduled_date: date) -> str:
    return f"自动定投：计划日 {scheduled_date.isoformat()}"


def _next_dca_date_on_or_after(base_date: date, frequency: Optional[str], dca_day: Optional[str]) -> date:
    if frequency == "weekly" or frequency == "biweekly":
        target_weekday = max(1, min(int(dca_day or 1), 7))
        days = (target_weekday - base_date.isoweekday()) % 7
        return base_date + timedelta(days=days)
    if frequency == "monthly":
        target_day = max(1, min(int(dca_day or 1), 28))
        candidate = base_date.replace(day=min(target_day, 28))
        if candidate < base_date:
            return _add_month(candidate, 1)
        return candidate
    return base_date


def _next_dca_date_after(current_date: date, frequency: Optional[str], dca_day: Optional[str]) -> date:
    if frequency == "weekly":
        return current_date + timedelta(days=7)
    if frequency == "biweekly":
        return current_date + timedelta(days=14)
    if frequency == "monthly":
        return _add_month(current_date.replace(day=max(1, min(int(dca_day or current_date.day), 28))), 1)
    return current_date + timedelta(days=1)


def _add_month(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month)


def _decimal(value: Optional[Union[Decimal, int, str]]) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _now() -> datetime:
    return datetime.now(timezone.utc)
