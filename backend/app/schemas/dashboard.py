from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class CategorySummary(BaseModel):
    assetType: str
    value: Decimal
    ratio: Decimal
    count: int


class DashboardSummary(BaseModel):
    totalAsset: Decimal
    totalDebt: Decimal
    netAsset: Decimal
    cashValue: Decimal
    fixedIncomeValue: Decimal
    equityValue: Decimal
    debtValue: Decimal
    assetCount: int
    activeAssetCount: int
    cashCoverageMonths: Optional[Decimal]
    monthNetAssetChange: Optional[Decimal] = None
    portfolioDrawdownPct: Optional[Decimal] = None
    dataStatus: str
    categorySummary: list[CategorySummary]
