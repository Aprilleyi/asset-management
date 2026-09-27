from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AlertRecordRead(BaseModel):
    id: str
    ownerId: str
    ruleId: str
    ruleCode: str
    alertLevel: str
    title: str
    description: Optional[str]
    targetAssetId: Optional[str]
    targetAssetName: Optional[str]
    currentValue: Optional[str]
    thresholdValue: Optional[str]
    unit: Optional[str]
    reason: str
    aiExplanation: Optional[str]
    status: str
    triggeredAt: datetime
    priceDate: Optional[date]
    dataSourceType: Optional[str]
    dataStatus: Optional[str]
    resolvedAt: Optional[datetime]
    userActionNote: Optional[str]
    createdAt: datetime
    updatedAt: datetime

    model_config = ConfigDict(from_attributes=True)


class AlertRecordList(BaseModel):
    items: list[AlertRecordRead]
    total: int
