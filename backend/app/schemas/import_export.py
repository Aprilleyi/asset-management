from typing import Any

from pydantic import BaseModel


class ImportRequest(BaseModel):
    confirmOverwrite: bool
    data: dict[str, Any]


class ImportResult(BaseModel):
    status: str
    importedCounts: dict[str, int]


class ExportResult(BaseModel):
    data: dict[str, Any]
