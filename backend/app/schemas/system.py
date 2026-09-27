from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DataSourceRead(BaseModel):
    id: str
    ownerId: str
    sourceType: str
    sourceName: str
    priority: int
    isEnabled: bool
    baseUrl: Optional[str]
    tokenEnvKey: Optional[str]
    supportedMarkets: Optional[str]
    lastSuccessAt: Optional[datetime]
    lastFailedAt: Optional[datetime]
    lastErrorMessage: Optional[str]
    healthStatus: str
    createdAt: datetime
    updatedAt: datetime

    model_config = ConfigDict(from_attributes=True)


class DataSourceList(BaseModel):
    items: list[DataSourceRead]
    total: int


class TaskLogRead(BaseModel):
    id: str
    ownerId: str
    taskType: str
    taskName: str
    status: str
    startedAt: datetime
    finishedAt: Optional[datetime]
    durationMs: Optional[int]
    successCount: Optional[int]
    failedCount: Optional[int]
    skippedCount: Optional[int]
    message: Optional[str]
    errorMessage: Optional[str]
    nextRunAt: Optional[datetime]
    createdAt: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskLogList(BaseModel):
    items: list[TaskLogRead]
    total: int
