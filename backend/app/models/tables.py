from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, DateTime, Numeric, Text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin(SQLModel):
    createdAt: datetime = Field(default_factory=utc_now)


class OwnedTimestampMixin(TimestampMixin):
    ownerId: str = Field(default="local_user", index=True)


class MutableOwnedTimestampMixin(OwnedTimestampMixin):
    updatedAt: datetime = Field(default_factory=utc_now)


class SchemaMigration(SQLModel, table=True):
    __tablename__ = "schema_migrations"

    id: str = Field(primary_key=True)
    version: str = Field(index=True)
    description: Optional[str] = None
    appliedAt: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Setting(MutableOwnedTimestampMixin, table=True):
    __tablename__ = "settings"

    id: str = Field(primary_key=True)
    settingKey: str = Field(index=True)
    settingName: str
    settingValue: str
    valueType: str
    unit: Optional[str] = None
    category: str
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    isEditable: bool = True


class AlertRule(MutableOwnedTimestampMixin, table=True):
    __tablename__ = "alert_rules"

    id: str = Field(primary_key=True)
    ruleCode: str = Field(index=True)
    ruleName: str
    category: str
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    metricKey: str
    operator: str
    thresholdValue: str
    thresholdUnit: Optional[str] = None
    alertLevel: str
    checkFrequency: str
    repeatIntervalDays: Optional[int] = None
    isEnabled: bool = True
    isEditable: bool = True
    isBuiltIn: bool = True


class Asset(MutableOwnedTimestampMixin, table=True):
    __tablename__ = "assets"

    id: str = Field(primary_key=True)
    name: str
    assetType: str = Field(index=True)
    subType: Optional[str] = None
    platform: str
    currency: str = "CNY"
    currentValue: Decimal = Field(default=0, sa_column=Column(Numeric(18, 4), nullable=False))
    costAmount: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 4)))
    holdingCostPrice: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 6)))
    holdingGain: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 4)))
    cumulativeGain: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 4)))
    cumulativeNetBasis: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 4)))
    principalAmount: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 4)))
    productCode: Optional[str] = Field(default=None, index=True)
    market: Optional[str] = None
    holdingShare: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 6)))
    latestPrice: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 6)))
    priceDate: Optional[date] = None
    dailyChangePct: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 4)))
    dailyIncomeAmount: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 4)))
    dataSourceType: Optional[str] = None
    dataStatus: str = "missing"
    priceErrorMessage: Optional[str] = Field(default=None, sa_column=Column(Text))
    expectedReturnRate: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 4)))
    entryDate: Optional[date] = Field(default=None, index=True)
    startDate: Optional[date] = None
    maturityDate: Optional[date] = None
    liquidityLevel: Optional[str] = None
    repaymentDate: Optional[date] = None
    interestRate: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 4)))
    isDca: bool = False
    dcaAmount: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 4)))
    dcaFrequency: Optional[str] = None
    dcaDay: Optional[str] = None
    dcaNextDate: Optional[date] = None
    dcaStatus: Optional[str] = None
    targetTag: Optional[str] = None
    note: Optional[str] = Field(default=None, sa_column=Column(Text))
    assetStatus: str = "active"


class Transaction(MutableOwnedTimestampMixin, table=True):
    __tablename__ = "transactions"

    id: str = Field(primary_key=True)
    assetId: str = Field(index=True)
    relatedAssetId: Optional[str] = Field(default=None, index=True)
    relatedTransactionId: Optional[str] = Field(default=None, index=True)
    transactionType: str
    amount: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    share: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 6)))
    price: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 6)))
    feeAmount: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 4)))
    feeRate: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 6)))
    tradeTiming: Optional[str] = None
    transactionDate: date
    source: str = "manual"
    note: Optional[str] = Field(default=None, sa_column=Column(Text))


class PriceRecord(OwnedTimestampMixin, table=True):
    __tablename__ = "price_records"

    id: str = Field(primary_key=True)
    assetId: Optional[str] = Field(default=None, index=True)
    productCode: str = Field(index=True)
    market: Optional[str] = None
    priceDate: date = Field(index=True)
    price: Decimal = Field(sa_column=Column(Numeric(18, 6), nullable=False))
    accumulatedNetValue: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 6)))
    dailyChangePct: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 4)))
    dailyIncomeAmount: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 4)))
    sourceType: str
    sourceName: Optional[str] = None
    fetchedAt: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    dataStatus: str
    isValid: bool = True
    errorMessage: Optional[str] = Field(default=None, sa_column=Column(Text))


class AlertRecord(MutableOwnedTimestampMixin, table=True):
    __tablename__ = "alert_records"

    id: str = Field(primary_key=True)
    ruleId: str = Field(index=True)
    ruleCode: str = Field(index=True)
    alertLevel: str
    title: str
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    targetAssetId: Optional[str] = Field(default=None, index=True)
    targetAssetName: Optional[str] = None
    currentValue: Optional[str] = None
    thresholdValue: Optional[str] = None
    unit: Optional[str] = None
    reason: str = Field(sa_column=Column(Text, nullable=False))
    aiExplanation: Optional[str] = Field(default=None, sa_column=Column(Text))
    status: str = "pending"
    triggeredAt: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    priceDate: Optional[date] = None
    dataSourceType: Optional[str] = None
    dataStatus: Optional[str] = None
    resolvedAt: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    userActionNote: Optional[str] = Field(default=None, sa_column=Column(Text))


class DailySnapshot(OwnedTimestampMixin, table=True):
    __tablename__ = "daily_snapshots"

    id: str = Field(primary_key=True)
    snapshotDate: date = Field(index=True)
    totalAsset: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    totalDebt: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    netAsset: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    cashValue: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    fixedIncomeValue: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    equityValue: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    debtValue: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    investmentValue: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 4)))
    cashRatio: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 4)))
    fixedIncomeRatio: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 4)))
    equityRatio: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 4)))
    debtRatio: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 4)))
    portfolioDrawdownPct: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 4)))
    dataStatus: str = "missing"


class MonthlyReview(MutableOwnedTimestampMixin, table=True):
    __tablename__ = "monthly_reviews"

    id: str = Field(primary_key=True)
    reviewMonth: str = Field(index=True)
    startSnapshotId: Optional[str] = None
    endSnapshotId: Optional[str] = None
    startNetAsset: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 4)))
    endNetAsset: Decimal = Field(sa_column=Column(Numeric(18, 4), nullable=False))
    netAssetChange: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 4)))
    investmentReturn: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 4)))
    newContribution: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(18, 4)))
    maxDrawdownPct: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(10, 4)))
    summaryText: str = Field(sa_column=Column(Text, nullable=False))
    riskReviewText: Optional[str] = Field(default=None, sa_column=Column(Text))
    dcaReviewText: Optional[str] = Field(default=None, sa_column=Column(Text))
    nextMonthFocusText: Optional[str] = Field(default=None, sa_column=Column(Text))
    dataCompletenessStatus: str
    generatedAt: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class DataSource(MutableOwnedTimestampMixin, table=True):
    __tablename__ = "data_sources"

    id: str = Field(primary_key=True)
    sourceType: str = Field(index=True)
    sourceName: str
    priority: int
    isEnabled: bool = True
    baseUrl: Optional[str] = None
    tokenEnvKey: Optional[str] = None
    supportedMarkets: Optional[str] = Field(default=None, sa_column=Column(Text))
    lastSuccessAt: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    lastFailedAt: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    lastErrorMessage: Optional[str] = Field(default=None, sa_column=Column(Text))
    healthStatus: str = "unconfigured"


class TaskLog(OwnedTimestampMixin, table=True):
    __tablename__ = "task_logs"

    id: str = Field(primary_key=True)
    taskType: str = Field(index=True)
    taskName: str
    status: str
    startedAt: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    finishedAt: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    durationMs: Optional[int] = None
    successCount: Optional[int] = None
    failedCount: Optional[int] = None
    skippedCount: Optional[int] = None
    message: Optional[str] = Field(default=None, sa_column=Column(Text))
    errorMessage: Optional[str] = Field(default=None, sa_column=Column(Text))
    nextRunAt: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class Backup(OwnedTimestampMixin, table=True):
    __tablename__ = "backups"

    id: str = Field(primary_key=True)
    backupType: str
    fileName: str
    filePath: str
    fileSizeBytes: Optional[int] = None
    dataVersion: str
    status: str
    errorMessage: Optional[str] = Field(default=None, sa_column=Column(Text))
