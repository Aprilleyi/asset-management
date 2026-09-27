from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.core.config import settings
from app.db.sqlite_backup import create_verified_backup
from app.models import Backup, Setting
from app.services.ids import make_id


def create_backup(session: Session, backup_type: str = "manual") -> Backup:
    source = _database_path(session)
    if not source.exists():
        raise FileNotFoundError(f"SQLite database not found: {source}")

    target, manifest = create_verified_backup(source, settings.backup_dir, backup_type, settings.data_version)

    backup = Backup(
        id=make_id("backup"),
        ownerId=settings.default_owner_id,
        backupType=backup_type,
        fileName=target.name,
        filePath=target.name,
        fileSizeBytes=manifest["fileSizeBytes"],
        dataVersion=settings.data_version,
        status="success",
    )
    session.add(backup)
    session.commit()
    session.refresh(backup)
    prune_old_backups(session)
    return backup


def list_backups(session: Session) -> list[Backup]:
    return list(
        session.exec(
            select(Backup)
            .where(Backup.ownerId == settings.default_owner_id)
            .order_by(Backup.createdAt.desc())
        ).all()
    )


def prune_old_backups(session: Session) -> int:
    retention_days = _retention_days(session)
    cutoff = _now() - timedelta(days=retention_days)
    old_backups = list(
        session.exec(
            select(Backup).where(
                Backup.ownerId == settings.default_owner_id,
                Backup.createdAt < cutoff,
            )
        ).all()
    )
    removed = 0
    for backup in old_backups:
        # Historical absolute paths remain untouched; only files created in
        # the configured backup directory can be pruned.
        if Path(backup.filePath).name != backup.filePath:
            continue
        target = settings.backup_dir / backup.filePath
        try:
            target.unlink(missing_ok=True)
            target.with_suffix(target.suffix + ".manifest.json").unlink(missing_ok=True)
        except OSError:
            continue
        session.delete(backup)
        removed += 1
    if removed:
        session.commit()
    return removed


def _database_path(session: Session) -> Path:
    bind = session.get_bind()
    database = getattr(bind.url, "database", None)
    if database:
        return Path(database)
    return settings.database_path


def _retention_days(session: Session) -> int:
    setting: Optional[Setting] = session.exec(
        select(Setting).where(
            Setting.ownerId == settings.default_owner_id,
            Setting.settingKey == "backup_retention_days",
        )
    ).first()
    if not setting:
        return 30
    try:
        return max(1, int(setting.settingValue))
    except ValueError:
        return 30


def _now() -> datetime:
    return datetime.now(timezone.utc)
