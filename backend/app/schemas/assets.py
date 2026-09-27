from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.core.messages import sanitize_data_error_message


ASSET_TYPES = {"cash", "fixed_income", "equity", "debt"}
ASSET_STATUSES = {"active", "inactive", "closed"}


class AssetBase(BaseModel):
    name: Optional[str] = Field(default=None, max_length=50)
    assetType: Optional[str] = None
    subType: Optional[str] = None
    platform: Optional[str] = None
    currency: str = "CNY"
    currentValue: Optional[Decimal] = None
    costAmount: Optional[Decimal] = None
    holdingCostPrice: Optional[Decimal] = None
    holdingGain: Optional[Decimal] = None
    cumulativeGain: Optional[Decimal] = None
    cumulativeNetBasis: Optional[Decimal] = None
    principalAmount: Optional[Decimal] = None
    productCode: Optional[str] = None
    market: Optional[str] = None
    holdingShare: Optional[Decimal] = None
    latestPrice: Optional[Decimal] = None
    priceDate: Optional[date] = None
    dailyChangePct: Optional[Decimal] = None
    dailyIncomeAmount: Optional[Decimal] = None
    dataSourceType: Optional[str] = None
    dataStatus: str = "missing"
    priceErrorMessage: Optional[str] = None
    expectedReturnRate: Optional[Decimal] = None
    entryDate: Optional[date] = None
    startDate: Optional[date] = None
    maturityDate: Optional[date] = None
    liquidityLevel: Optional[str] = None
    repaymentDate: Optional[date] = None
    interestRate: Optional[Decimal] = None
    isDca: bool = False
    dcaAmount: Optional[Decimal] = None
    dcaFrequency: Optional[str] = None
    dcaDay: Optional[str] = None
    dcaNextDate: Optional[date] = None
    dcaStatus: Optional[str] = None
    targetTag: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=500)
    assetStatus: str = "active"

    @field_validator("name", "platform", mode="before")
    @classmethod
    def strip_required_strings(cls, value: Optional[str]) -> Optional[str]:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("assetType")
    @classmethod
    def validate_asset_type(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in ASSET_TYPES:
            raise ValueError("assetType must be one of cash, fixed_income, equity, debt")
        return value

    @field_validator("assetStatus")
    @classmethod
    def validate_asset_status(cls, value: str) -> str:
        if value not in ASSET_STATUSES:
            raise ValueError("assetStatus must be one of active, inactive, closed")
        return value


class AssetCreate(AssetBase):
    name: str = Field(max_length=50)
    assetType: str
    platform: str
    currentValue: Decimal = Decimal("0")


class AssetUpdate(AssetBase):
    pass


class AssetRead(BaseModel):
    id: str
    ownerId: str
    name: str
    assetType: str
    subType: Optional[str]
    platform: str
    currency: str
    currentValue: Decimal
    costAmount: Optional[Decimal]
    holdingCostPrice: Optional[Decimal]
    holdingGain: Optional[Decimal]
    cumulativeGain: Optional[Decimal]
    cumulativeNetBasis: Optional[Decimal]
    principalAmount: Optional[Decimal]
    productCode: Optional[str]
    market: Optional[str]
    holdingShare: Optional[Decimal]
    latestPrice: Optional[Decimal]
    priceDate: Optional[date]
    dailyChangePct: Optional[Decimal]
    dailyIncomeAmount: Optional[Decimal]
    dataSourceType: Optional[str]
    dataStatus: str
    priceErrorMessage: Optional[str]
    expectedReturnRate: Optional[Decimal]
    entryDate: Optional[date]
    startDate: Optional[date]
    maturityDate: Optional[date]
    liquidityLevel: Optional[str]
    repaymentDate: Optional[date]
    interestRate: Optional[Decimal]
    isDca: bool
    dcaAmount: Optional[Decimal]
    dcaFrequency: Optional[str]
    dcaDay: Optional[str]
    dcaNextDate: Optional[date]
    dcaStatus: Optional[str]
    targetTag: Optional[str]
    note: Optional[str]
    assetStatus: str
    createdAt: datetime
    updatedAt: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("priceErrorMessage")
    def serialize_price_error_message(self, value: Optional[str]) -> Optional[str]:
        return sanitize_data_error_message(value)


class AssetList(BaseModel):
    items: list[AssetRead]
    total: int
