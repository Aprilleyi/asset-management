from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TaskStatusRead(BaseModel):
    taskType: str
    taskName: str
    isEnabled: bool
    lastRunAt: Optional[datetime]
    nextRunAt: Optional[datetime]
    lastStatus: Optional[str]
    lastMessage: Optional[str]
    errorMessage: Optional[str]


class TaskStatusList(BaseModel):
    items: list[TaskStatusRead]
    total: int


class TaskRunResponse(BaseModel):
    taskLogId: str
    taskType: str
    status: str
    message: Optional[str]
    errorMessage: Optional[str]
    successCount: int = 0
    failedCount: int = 0
