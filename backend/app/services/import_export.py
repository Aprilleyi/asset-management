from datetime import datetime, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete
from sqlmodel import Session, select

from app.core.config import settings
from app.models import (
    AlertRecord,
    AlertRule,
    Asset,
    Backup,
    DailySnapshot,
    DataSource,
    MonthlyReview,
    PriceRecord,
    SchemaMigration,
    Setting,
    TaskLog,
    Transaction,
)


EXPORT_TABLES = [
    ("assets", Asset),
    ("transactions", Transaction),
    ("priceRecords", PriceRecord),
    ("alertRules", AlertRule),
    ("alertRecords", AlertRecord),
    ("dailySnapshots", DailySnapshot),
    ("monthlyReviews", MonthlyReview),
    ("settings", Setting),
    ("dataSources", DataSource),
    ("taskLogs", TaskLog),
    ("backups", Backup),
    ("schemaMigrations", SchemaMigration),
]

REQUIRED_EXPORT_KEYS = {
    "dataVersion",
    "exportedAt",
    "ownerId",
    "assets",
    "transactions",
    "priceRecords",
    "alertRules",
    "alertRecords",
    "dailySnapshots",
    "monthlyReviews",
    "settings",
    "dataSources",
    "taskLogs",
    "backups",
}


def export_data(session: Session) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dataVersion": settings.data_version,
        "exportedAt": _now().isoformat(),
        "ownerId": settings.default_owner_id,
    }
    for key, model in EXPORT_TABLES:
        items = session.exec(select(model)).all()
        encoded = jsonable_encoder(items)
        if key == "dataSources":
            encoded = [_sanitize_data_source(item) for item in encoded]
        payload[key] = encoded
    return payload


def import_data(session: Session, payload: dict[str, Any], confirm_overwrite: bool) -> dict[str, int]:
    if not confirm_overwrite:
        raise ValueError("导入会覆盖当前数据，请先确认 confirmOverwrite=true。")
    _validate_payload(payload)
    prepared = _prepare_rows(payload)

    imported_counts: dict[str, int] = {}
    try:
        for _, model in reversed(EXPORT_TABLES):
            session.exec(delete(model))
        for key, model in EXPORT_TABLES:
            rows = prepared.get(key, [])
            for row in rows:
                session.add(model.model_validate(row))
            imported_counts[key] = len(rows)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return imported_counts


def _validate_payload(payload: dict[str, Any]) -> None:
    missing = REQUIRED_EXPORT_KEYS - set(payload.keys())
    if missing:
        raise ValueError(f"导入数据缺少必要字段：{', '.join(sorted(missing))}")
    legacy_mislabeled_export = (
        payload.get("dataVersion") == "1.0.0"
        and isinstance(payload.get("schemaMigrations"), list)
        and any(isinstance(row, dict) and row.get("version") == "1.4.0" for row in payload["schemaMigrations"])
    )
    if payload.get("dataVersion") != settings.data_version and not legacy_mislabeled_export:
        raise ValueError(
            f"导入数据版本 {payload.get('dataVersion')} 与当前版本 {settings.data_version} 不一致。"
        )
    if payload.get("ownerId") != settings.default_owner_id:
        raise ValueError("导入数据 ownerId 与当前本地用户不一致。")
    for key, _ in EXPORT_TABLES:
        if key == "schemaMigrations":
            continue
        if key not in payload:
            raise ValueError(f"导入数据缺少必要字段：{key}")
        if not isinstance(payload[key], list):
            raise ValueError(f"导入字段 {key} 必须是数组。")


def _prepare_rows(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    prepared: dict[str, list[dict[str, Any]]] = {}
    for key, model in EXPORT_TABLES:
        rows = payload.get(key, [])
        if not isinstance(rows, list):
            raise ValueError(f"导入字段 {key} 必须是数组。")
        prepared_rows = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"{key}[{index}] 必须是对象。")
            row = dict(row)
            if key == "dataSources":
                row.pop("token", None)
                row.pop("tokenEnvKey", None)
            try:
                model.model_validate(row)
            except Exception as exc:
                raise ValueError(f"{key}[{index}] 校验失败：{exc}") from exc
            prepared_rows.append(row)
        prepared[key] = prepared_rows
    return prepared


def _sanitize_data_source(item: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(item)
    sanitized.pop("token", None)
    sanitized.pop("tokenEnvKey", None)
    return sanitized


def _now() -> datetime:
    return datetime.now(timezone.utc)
