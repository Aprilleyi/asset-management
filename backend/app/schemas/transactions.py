from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


TRANSACTION_TYPES = {"buy", "sell", "convert_in", "convert_out", "cash_dividend", "dca"}
MANUAL_TRANSACTION_TYPES = {"buy", "sell", "cash_dividend"}


class TransactionRead(BaseModel):
    id: str
    ownerId: str
    assetId: str
    relatedAssetId: Optional[str]
    relatedTransactionId: Optional[str]
    transactionType: str
    amount: Optional[Decimal] = None
    share: Optional[Decimal]
    price: Optional[Decimal]
    feeAmount: Optional[Decimal]
    feeRate: Optional[Decimal]
    tradeTiming: Optional[str]
    transactionDate: date
    source: str
    note: Optional[str]
    createdAt: datetime
    updatedAt: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionList(BaseModel):
    items: list[TransactionRead]
    total: int


class TransactionUpdate(BaseModel):
    amount: Optional[Decimal] = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is not None and value <= 0:
            raise ValueError("amount must be greater than 0")
        return value


class TransactionCreate(BaseModel):
    transactionType: str
    amount: Decimal
    share: Optional[Decimal] = None
    price: Optional[Decimal] = None
    feeAmount: Optional[Decimal] = None
    feeRate: Optional[Decimal] = None
    tradeTiming: str = "before_15"
    transactionDate: date
    source: str = "manual"
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("transactionType")
    @classmethod
    def validate_transaction_type(cls, value: str) -> str:
        if value not in MANUAL_TRANSACTION_TYPES:
            raise ValueError("transactionType must be one of buy, sell, cash_dividend")
        return value

    @field_validator("amount", "share", "price", "feeAmount", "feeRate")
    @classmethod
    def validate_non_negative_decimal(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is not None and value < 0:
            raise ValueError("numeric fields must be greater than or equal to 0")
        return value

    @field_validator("tradeTiming")
    @classmethod
    def validate_trade_timing(cls, value: str) -> str:
        if value not in {"before_15", "after_15"}:
            raise ValueError("tradeTiming must be before_15 or after_15")
        return value

    @model_validator(mode="after")
    def validate_amount(self) -> "TransactionCreate":
        if self.transactionType == "buy" and (self.amount is None or self.amount <= 0) and (self.share is None or self.share <= 0):
            raise ValueError("amount or share is required for buy transactions")
        if self.transactionType == "sell" and (self.share is None or self.share <= 0) and (self.amount is None or self.amount <= 0):
            raise ValueError("share or amount is required for sell transactions")
        if self.transactionType == "cash_dividend" and (self.amount is None or self.amount <= 0):
            raise ValueError("amount must be greater than 0 for cash_dividend transactions")
        return self


class ConversionCreate(BaseModel):
    targetAssetId: str
    transactionDate: date
    outAmount: Decimal
    outShare: Optional[Decimal] = None
    outPrice: Optional[Decimal] = None
    inAmount: Optional[Decimal] = None
    inShare: Optional[Decimal] = None
    inPrice: Optional[Decimal] = None
    feeAmount: Optional[Decimal] = None
    feeRate: Optional[Decimal] = None
    tradeTiming: str = "before_15"
    source: str = "manual"
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("outAmount", "outShare", "outPrice", "inAmount", "inShare", "inPrice", "feeAmount", "feeRate")
    @classmethod
    def validate_non_negative_decimal(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is not None and value < 0:
            raise ValueError("numeric fields must be greater than or equal to 0")
        return value

    @field_validator("tradeTiming")
    @classmethod
    def validate_trade_timing(cls, value: str) -> str:
        if value not in {"before_15", "after_15"}:
            raise ValueError("tradeTiming must be before_15 or after_15")
        return value

    @model_validator(mode="after")
    def validate_conversion(self) -> "ConversionCreate":
        if self.outAmount <= 0:
            raise ValueError("outAmount must be greater than 0")
        if not self.targetAssetId:
            raise ValueError("targetAssetId is required")
        return self


class ConversionRead(BaseModel):
    outTransaction: TransactionRead
    inTransaction: TransactionRead
