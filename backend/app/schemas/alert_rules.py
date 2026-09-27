from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AlertRuleUpdate(BaseModel):
    isEnabled: Optional[bool] = None
    thresholdValue: Optional[str] = None
    alertLevel: Optional[str] = None
    repeatIntervalDays: Optional[int] = Field(default=None, ge=0)


class AlertRuleRead(BaseModel):
    id: str
    ownerId: str
    ruleCode: str
    ruleName: str
    category: str
    description: Optional[str]
    metricKey: str
    operator: str
    thresholdValue: str
    thresholdUnit: Optional[str]
    alertLevel: str
    checkFrequency: str
    repeatIntervalDays: Optional[int]
    isEnabled: bool
    isEditable: bool
    isBuiltIn: bool
    createdAt: datetime
    updatedAt: datetime

    model_config = ConfigDict(from_attributes=True)


class AlertRuleList(BaseModel):
    items: list[AlertRuleRead]
    total: int
