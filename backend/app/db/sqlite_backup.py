"""Verified SQLite online backup and staged restore primitives."""

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4


CORE_TABLES = (
    "assets",
    "transactions",
    "price_records",
    "daily_snapshots",
    "alert_records",
    "monthly_reviews",
    "settings",
    "alert_rules",
    "data_sources",
    "task_logs",
    "backups",
    "schema_migrations",
)


def _readonly(path: Path) -> sqlite3.Connection:
    path = path.resolve(strict=True)
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)


def database_facts(path: Path) -> dict:
    with closing(_readonly(path)) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if result != ("ok",):
            raise ValueError(f"SQLite integrity_check failed: {result}")
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = set(CORE_TABLES) - names
        if missing:
            raise ValueError(f"Missing core tables: {', '.join(sorted(missing))}")
        counts = {name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in CORE_TABLES}
        versions = [row[0] for row in connection.execute("SELECT version FROM schema_migrations")]
        if not versions:
            raise ValueError("Missing schema migration history")
        alembic_revisions = [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")] if "alembic_version" in names else []
        return {
            "schemaVersion": max(versions, key=lambda value: tuple(int(part) for part in value.split("."))),
            "alembicRevisions": sorted(alembic_revisions),
            "rowCounts": counts,
        }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _online_copy(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(_readonly(source)) as source_db, closing(sqlite3.connect(destination)) as target_db:
        os.chmod(destination, 0o600)
        source_db.backup(target_db)


def _write_json_exclusive(path: Path, payload: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def create_verified_backup(source: Path, backup_dir: Path, backup_type: str, data_version: str) -> tuple[Path, dict]:
    if backup_type not in {"manual", "auto", "migration", "rollback"}:
        raise ValueError("Unsupported backup type")
    if not source.is_file():
        raise FileNotFoundError(source)
    backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    target = backup_dir / f"asset_manager_{backup_type}_{stamp}_{uuid4().hex[:8]}.sqlite3"
    temporary = backup_dir / f".{target.name}.new"
    try:
        _online_copy(source, temporary)
        facts = database_facts(temporary)
        manifest = {
            **facts,
            "dataVersion": data_version,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "fileName": target.name,
            "fileSizeBytes": temporary.stat().st_size,
            "sha256": file_sha256(temporary),
        }
        os.link(temporary, target)
        temporary.unlink()
        _write_json_exclusive(target.with_suffix(target.suffix + ".manifest.json"), manifest)
        return target, manifest
    finally:
        temporary.unlink(missing_ok=True)


def verify_backup(backup: Path) -> dict:
    manifest_path = backup.with_suffix(backup.suffix + ".manifest.json")
    with manifest_path.open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    if manifest.get("fileName") != backup.name:
        raise ValueError("Backup filename does not match manifest")
    if manifest.get("fileSizeBytes") != backup.stat().st_size or manifest.get("sha256") != file_sha256(backup):
        raise ValueError("Backup checksum or size does not match manifest")
    facts = database_facts(backup)
    if any(facts[key] != manifest.get(key) for key in ("schemaVersion", "alembicRevisions", "rowCounts")):
        raise ValueError("Backup schema or core row counts do not match manifest")
    return manifest


def restore_staged(
    backup: Path,
    destination: Path,
    promote: bool = False,
    replace_existing: bool = False,
    rollback_dir: Optional[Path] = None,
) -> Path:
    """Restore into destination.new; promotion is opt-in and preserves an existing destination."""
    manifest = verify_backup(backup)
    destination = destination.resolve()
    staged = destination.with_name(destination.name + ".new")
    staged_manifest = staged.with_suffix(staged.suffix + ".manifest.json")
    if staged.exists() and not promote:
        raise FileExistsError(staged)
    created_stage = not staged.exists()
    try:
        if created_stage:
            _online_copy(backup, staged)
        else:
            with staged_manifest.open(encoding="utf-8") as stream:
                stage_record = json.load(stream)
            if stage_record.get("backupSha256") != manifest["sha256"] or stage_record.get("sha256") != file_sha256(staged):
                raise ValueError("Staged restore does not match the verified backup")
        staged_facts = database_facts(staged)
        if any(staged_facts[key] != manifest[key] for key in ("schemaVersion", "alembicRevisions", "rowCounts")):
            raise ValueError("Restored schema or counts differ from backup")
        if created_stage:
            _write_json_exclusive(staged_manifest, {"backupSha256": manifest["sha256"], "sha256": file_sha256(staged)})
        if not promote:
            return staged
        if destination.exists():
            if not replace_existing:
                raise FileExistsError("Destination exists; explicit replace_existing is required")
            if rollback_dir is None:
                raise ValueError("rollback_dir is required when replacing an existing database")
            create_verified_backup(destination, rollback_dir, "rollback", manifest["dataVersion"])
        os.replace(staged, destination)
        staged_manifest.unlink(missing_ok=True)
        return destination
    except Exception:
        if created_stage:
            staged.unlink(missing_ok=True)
            staged_manifest.unlink(missing_ok=True)
        raise
