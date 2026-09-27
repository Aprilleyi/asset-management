from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class BackupRead(BaseModel):
    id: str
    ownerId: str
    backupType: str
    fileName: str
    filePath: str
    fileSizeBytes: Optional[int]
    dataVersion: str
    status: str
    errorMessage: Optional[str]
    createdAt: datetime

    model_config = ConfigDict(from_attributes=True)


class BackupList(BaseModel):
    items: list[BackupRead]
    total: int
