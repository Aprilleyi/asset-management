from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SettingUpdate(BaseModel):
    settingValue: str


class SettingRead(BaseModel):
    id: str
    ownerId: str
    settingKey: str
    settingName: str
    settingValue: str
    valueType: str
    unit: Optional[str]
    category: str
    description: Optional[str]
    isEditable: bool
    createdAt: datetime
    updatedAt: datetime

    model_config = ConfigDict(from_attributes=True)


class SettingList(BaseModel):
    items: list[SettingRead]
    total: int
