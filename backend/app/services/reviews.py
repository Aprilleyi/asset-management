from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from app.core.config import settings
from app.models import AlertRecord, Asset, DailySnapshot, MonthlyReview, PriceRecord, Transaction
from app.services.ids import make_id


INFLOW_TYPES = {"buy", "deposit", "transfer_in", "contribution", "dca", "add"}
OUTFLOW_TYPES = {"sell", "withdraw", "transfer_out", "redeem", "reduce"}


def generate_monthly_review(session: Session, review_month: Optional[str] = None) -> MonthlyReview:
    month = review_month or date.today().strftime("%Y-%m")
    start_date, end_date = _month_bounds(month)
    start_snapshot = session.exec(
        select(DailySnapshot).where(
            DailySnapshot.ownerId == settings.default_owner_id,
            DailySnapshot.snapshotDate == start_date,
        )
    ).first()
    end_snapshot = session.exec(
        select(DailySnapshot)
        .where(
            DailySnapshot.ownerId == settings.default_owner_id,
            DailySnapshot.snapshotDate >= start_date,
            DailySnapshot.snapshotDate <= end_date,
        )
        .order_by(DailySnapshot.snapshotDate.desc())
    ).first()

    if not end_snapshot:
        end_snapshot = session.exec(
            select(DailySnapshot)
            .where(DailySnapshot.ownerId == settings.default_owner_id)
            .order_by(DailySnapshot.snapshotDate.desc())
        ).first()

    if not end_snapshot:
        raise ValueError("没有可用于生成复盘的每日快照，请先运行每日快照任务。")

    transactions = _month_transactions(session, start_date, end_date)
    alerts = _month_alerts(session, start_date, end_date)
    prices = _month_prices(session, start_date, end_date)
    assets = _active_assets(session)
    max_drawdown = _max_drawdown(session, start_date, end_date)

    if not start_snapshot:
        data_status = "history_insufficient"
        start_net = None
        net_change = None
        new_contribution = None
        investment_return = None
        summary = (
            f"{month} 复盘已基于真实资产、提醒、行情和可用快照生成；"
            f"但缺少 {start_date.isoformat()} 的月初快照，不能计算月初净资产、净资产变化或投资收益。"
        )
    else:
        data_status = "complete"
        start_net = start_snapshot.netAsset
        net_change = end_snapshot.netAsset - start_snapshot.netAsset
        new_contribution = _net_contribution(transactions)
        investment_return = net_change - new_contribution
        summary = (
            f"{month} 月末净资产 {end_snapshot.netAsset:.2f}，"
            f"较月初变化 {net_change:.2f}；其中新增投入净额 {new_contribution:.2f}，"
            f"估算投资收益 {investment_return:.2f}。"
        )

    review = _upsert_review(
        session=session,
        review_month=month,
        start_snapshot=start_snapshot,
        end_snapshot=end_snapshot,
        start_net=start_net,
        net_change=net_change,
        new_contribution=new_contribution,
        investment_return=investment_return,
        max_drawdown=max_drawdown,
        summary=summary,
        risk_review=_risk_review(alerts, prices),
        dca_review=_dca_review(assets, transactions),
        next_focus=_next_focus(alerts, prices, data_status),
        data_status=data_status,
    )
    session.commit()
    session.refresh(review)
    return review


def _upsert_review(
    session: Session,
    review_month: str,
    start_snapshot: Optional[DailySnapshot],
    end_snapshot: DailySnapshot,
    start_net: Optional[Decimal],
    net_change: Optional[Decimal],
    new_contribution: Optional[Decimal],
    investment_return: Optional[Decimal],
    max_drawdown: Optional[Decimal],
    summary: str,
    risk_review: str,
    dca_review: str,
    next_focus: str,
    data_status: str,
) -> MonthlyReview:
    review = session.exec(
        select(MonthlyReview).where(
            MonthlyReview.ownerId == settings.default_owner_id,
            MonthlyReview.reviewMonth == review_month,
        )
    ).first()
    if not review:
        review = MonthlyReview(
            id=make_id("review"),
            ownerId=settings.default_owner_id,
            reviewMonth=review_month,
            endNetAsset=end_snapshot.netAsset,
            summaryText=summary,
            dataCompletenessStatus=data_status,
            generatedAt=_now(),
        )
    review.startSnapshotId = start_snapshot.id if start_snapshot else None
    review.endSnapshotId = end_snapshot.id
    review.startNetAsset = start_net
    review.endNetAsset = end_snapshot.netAsset
    review.netAssetChange = net_change
    review.newContribution = new_contribution
    review.investmentReturn = investment_return
    review.maxDrawdownPct = max_drawdown
    review.summaryText = summary
    review.riskReviewText = risk_review
    review.dcaReviewText = dca_review
    review.nextMonthFocusText = next_focus
    review.dataCompletenessStatus = data_status
    review.generatedAt = _now()
    review.updatedAt = _now()
    session.add(review)
    return review


def _dca_review(assets: list[Asset], transactions: list[Transaction]) -> str:
    dca_assets = [asset for asset in assets if asset.isDca]
    if not dca_assets:
        return "本月未识别到启用定投的资产。"
    lines = []
    for asset in dca_assets:
        cumulative = sum(
            transaction.amount
            for transaction in transactions
            if transaction.assetId == asset.id and transaction.transactionType in INFLOW_TYPES
        )
        if cumulative <= 0:
            cumulative = asset.costAmount or Decimal("0")
        current_value = asset.currentValue or Decimal("0")
        gain = current_value - cumulative
        gain_rate = gain / cumulative * Decimal("100") if cumulative > 0 else None
        avg_cost = cumulative / asset.holdingShare if asset.holdingShare and asset.holdingShare > 0 else None
        lines.append(
            f"{asset.name}：定投金额 {asset.dcaAmount or Decimal('0'):.2f}，累计投入 {cumulative:.2f}，"
            f"当前市值 {current_value:.2f}，收益 {gain:.2f}，"
            f"收益率 {_pct(gain_rate)}，平均成本 {_money(avg_cost)}。"
        )
    return "\n".join(lines)


def _risk_review(alerts: list[AlertRecord], prices: list[PriceRecord]) -> str:
    strong_count = sum(1 for alert in alerts if alert.alertLevel == "strong")
    must_count = sum(1 for alert in alerts if alert.alertLevel == "must")
    failed_prices = sum(1 for price in prices if not price.isValid)
    return (
        f"本月强提醒 {strong_count} 条，必须关注提醒 {must_count} 条；"
        f"行情记录 {len(prices)} 条，其中失败或无效 {failed_prices} 条。"
    )


def _next_focus(alerts: list[AlertRecord], prices: list[PriceRecord], data_status: str) -> str:
    focus = []
    if data_status == "history_insufficient":
        focus.append("补齐并持续生成每日快照，以便后续区分净资产变化和投资收益。")
    pending_alerts = [alert for alert in alerts if alert.status == "pending"]
    if pending_alerts:
        focus.append(f"观察 {len(pending_alerts)} 条未处理提醒的状态变化。")
    if any(not price.isValid for price in prices):
        focus.append("关注行情数据源稳定性，必要时使用手动补录兜底。")
    if not focus:
        focus.append("继续观察资产结构、现金覆盖月数和行情数据质量。")
    return " ".join(focus)


def _month_transactions(session: Session, start_date: date, end_date: date) -> list[Transaction]:
    return list(
        session.exec(
            select(Transaction).where(
                Transaction.ownerId == settings.default_owner_id,
                Transaction.transactionDate >= start_date,
                Transaction.transactionDate <= end_date,
            )
        ).all()
    )


def _month_alerts(session: Session, start_date: date, end_date: date) -> list[AlertRecord]:
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
    return list(
        session.exec(
            select(AlertRecord).where(
                AlertRecord.ownerId == settings.default_owner_id,
                AlertRecord.triggeredAt >= start_dt,
                AlertRecord.triggeredAt <= end_dt,
            )
        ).all()
    )


def _month_prices(session: Session, start_date: date, end_date: date) -> list[PriceRecord]:
    return list(
        session.exec(
            select(PriceRecord).where(
                PriceRecord.ownerId == settings.default_owner_id,
                PriceRecord.priceDate >= start_date,
                PriceRecord.priceDate <= end_date,
            )
        ).all()
    )


def _active_assets(session: Session) -> list[Asset]:
    return list(
        session.exec(
            select(Asset).where(
                Asset.ownerId == settings.default_owner_id,
                Asset.assetStatus != "inactive",
            )
        ).all()
    )


def _net_contribution(transactions: list[Transaction]) -> Decimal:
    total = Decimal("0")
    for transaction in transactions:
        if transaction.transactionType in INFLOW_TYPES:
            total += transaction.amount
        elif transaction.transactionType in OUTFLOW_TYPES:
            total -= transaction.amount
    return total


def _max_drawdown(session: Session, start_date: date, end_date: date) -> Optional[Decimal]:
    snapshots = list(
        session.exec(
            select(DailySnapshot)
            .where(
                DailySnapshot.ownerId == settings.default_owner_id,
                DailySnapshot.snapshotDate >= start_date,
                DailySnapshot.snapshotDate <= end_date,
            )
            .order_by(DailySnapshot.snapshotDate)
        ).all()
    )
    high: Optional[Decimal] = None
    max_drawdown: Optional[Decimal] = None
    for snapshot in snapshots:
        value = snapshot.investmentValue
        if value is None or value <= 0:
            continue
        high = value if high is None else max(high, value)
        drawdown = (high - value) / high * Decimal("100")
        max_drawdown = drawdown if max_drawdown is None else max(max_drawdown, drawdown)
    return max_drawdown


def _month_bounds(month: str) -> tuple[date, date]:
    year, month_number = [int(part) for part in month.split("-")]
    last_day = monthrange(year, month_number)[1]
    return date(year, month_number, 1), date(year, month_number, last_day)


def _pct(value: Optional[Decimal]) -> str:
    return "-" if value is None else f"{value:.2f}%"


def _money(value: Optional[Decimal]) -> str:
    return "-" if value is None else f"{value:.2f}"


def _now() -> datetime:
    return datetime.now(timezone.utc)
