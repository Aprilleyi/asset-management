from datetime import date
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class FundBasicInfo(BaseModel):
    productCode: str
    assetType: Optional[str] = None
    subType: Optional[str] = None
    name: Optional[str] = None
    market: str = "CN_FUND"
    latestPrice: Optional[Decimal] = None
    priceDate: Optional[date] = None
    dailyChangePct: Optional[Decimal] = None
    sourceType: str = "akshare"
    dataStatus: str
    errorMessage: Optional[str] = None


class ScreenshotParseRequest(BaseModel):
    fileName: str = Field(min_length=1, max_length=200)
    imageBase64: str = Field(min_length=1)

    @field_validator("imageBase64", mode="before")
    @classmethod
    def strip_data_url_prefix(cls, value: str) -> str:
        if isinstance(value, str) and "," in value and value.startswith("data:"):
            return value.split(",", 1)[1]
        return value


class ScreenshotParseResult(BaseModel):
    status: str
    message: str
    draft: dict[str, Any] = Field(default_factory=dict)
    rawText: Optional[str] = None


class BenchmarkPoint(BaseModel):
    priceDate: date
    close: Decimal
    dailyChangePct: Optional[Decimal] = None


class BenchmarkHistory(BaseModel):
    code: str
    name: str
    sourceType: str = "akshare"
    dataStatus: str
    errorMessage: Optional[str] = None
    items: list[BenchmarkPoint] = Field(default_factory=list)
