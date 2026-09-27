from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MonthlyReviewGenerateRequest(BaseModel):
    reviewMonth: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}$",
        description="YYYY-MM. Defaults to the current month.",
    )


class MonthlyReviewRead(BaseModel):
    id: str
    ownerId: str
    reviewMonth: str
    startSnapshotId: Optional[str]
    endSnapshotId: Optional[str]
    startNetAsset: Optional[Decimal]
    endNetAsset: Decimal
    netAssetChange: Optional[Decimal]
    investmentReturn: Optional[Decimal]
    newContribution: Optional[Decimal]
    maxDrawdownPct: Optional[Decimal]
    summaryText: str
    riskReviewText: Optional[str]
    dcaReviewText: Optional[str]
    nextMonthFocusText: Optional[str]
    dataCompletenessStatus: str
    generatedAt: datetime
    createdAt: datetime
    updatedAt: datetime

    model_config = ConfigDict(from_attributes=True)


class MonthlyReviewList(BaseModel):
    items: list[MonthlyReviewRead]
    total: int
