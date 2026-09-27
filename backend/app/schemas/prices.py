from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.core.messages import sanitize_data_error_message


class ManualPriceCreate(BaseModel):
    priceDate: date
    price: Decimal = Field(gt=0)
    currentValue: Optional[Decimal] = Field(default=None, ge=0)
    dailyChangePct: Optional[Decimal] = None
    dailyIncomeAmount: Optional[Decimal] = None
    sourceName: str = "手动补录"


class PriceRecordRead(BaseModel):
    id: str
    ownerId: str
    assetId: Optional[str]
    productCode: str
    market: Optional[str]
    priceDate: Optional[date]
    price: Optional[Decimal]
    dailyChangePct: Optional[Decimal]
    dailyIncomeAmount: Optional[Decimal]
    sourceType: str
    sourceName: Optional[str]
    fetchedAt: datetime
    dataStatus: str
    isValid: bool
    errorMessage: Optional[str]
    createdAt: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("errorMessage")
    def serialize_error_message(self, value: Optional[str]) -> Optional[str]:
        return sanitize_data_error_message(value)


class PriceRecordList(BaseModel):
    items: list[PriceRecordRead]
    total: int


class PriceUpdateResult(BaseModel):
    assetId: str
    productCode: Optional[str]
    success: bool
    priceRecord: PriceRecordRead


class PriceUpdateRunResult(BaseModel):
    taskLogId: str
    status: str
    successCount: int
    failedCount: int
    items: list[PriceUpdateResult]
