import json
import sqlite3
from pathlib import Path

import pytest

from app.core.config import Settings, settings
from app.db.migrate import baseline, status, upgrade, validate_baseline
from app.db.sqlite_backup import create_verified_backup, database_facts, restore_staged, verify_backup
from app.main import app


def test_new_database_migrates_and_existing_baseline_can_be_stamped(tmp_path: Path):
    database = tmp_path / "fresh.sqlite3"
    upgrade(database)
    facts = database_facts(database)
    assert facts["schemaVersion"] == "1.4.0"
    assert facts["rowCounts"]["settings"] == 14
    status(database)

    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE alembic_version")
    validate_baseline(database)
    with pytest.raises(ValueError, match="baseline"):
        upgrade(database)
    baseline(database)
    status(database)


def test_online_backup_and_staged_restore(tmp_path: Path):
    source = tmp_path / "source.sqlite3"
    upgrade(source)
    with sqlite3.connect(source) as connection:
        connection.execute(
            'INSERT INTO assets ("createdAt", "ownerId", "updatedAt", id, name, "assetType", platform, currency, "currentValue", "isDca", "assetStatus", "dataStatus") '
            "VALUES ('2026-01-01', 'local_user', '2026-01-01', 'test_asset', 'Test', 'cash', 'Test', 'CNY', 100, 0, 'active', 'missing')"
        )
    backup, manifest = create_verified_backup(source, tmp_path / "backups", "manual", "1.4.0")
    assert manifest["rowCounts"]["assets"] == 1
    assert len(manifest["sha256"]) == 64
    assert verify_backup(backup) == manifest
    assert str(tmp_path) not in json.dumps(manifest)

    destination = tmp_path / "restored.sqlite3"
    staged = restore_staged(backup, destination)
    assert staged.name == "restored.sqlite3.new"
    assert not destination.exists()
    assert database_facts(staged)["rowCounts"]["assets"] == 1
    restored = restore_staged(backup, destination, promote=True)
    assert restored == destination
    assert database_facts(destination)["rowCounts"]["assets"] == 1

    with pytest.raises(FileExistsError):
        restore_staged(backup, destination, promote=True)
    with sqlite3.connect(destination) as connection:
        connection.execute(
            'INSERT INTO assets ("createdAt", "ownerId", "updatedAt", id, name, "assetType", platform, currency, "currentValue", "isDca", "assetStatus", "dataStatus") '
            "VALUES ('2026-01-01', 'local_user', '2026-01-01', 'second_asset', 'Second', 'cash', 'Test', 'CNY', 200, 0, 'active', 'missing')"
        )
    with pytest.raises(ValueError, match="rollback_dir"):
        restore_staged(backup, destination, promote=True, replace_existing=True)
    restore_staged(backup, destination, promote=True, replace_existing=True, rollback_dir=tmp_path / "rollback")
    assert database_facts(destination)["rowCounts"]["assets"] == 1
    rollback_files = list((tmp_path / "rollback").glob("*.sqlite3"))
    assert len(rollback_files) == 1
    assert database_facts(rollback_files[0])["rowCounts"]["assets"] == 2
    manifest_path = backup.with_suffix(backup.suffix + ".manifest.json")
    original = manifest_path.read_text()
    manifest_path.write_text(original.replace('"sha256": "', '"sha256": "bad'))
    with pytest.raises(ValueError, match="checksum"):
        verify_backup(backup)


def test_environment_switch_and_scheduler_disabled(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ASSET_MANAGER_DATABASE_PATH", str(tmp_path / "asset_prod.sqlite3"))
    monkeypatch.setenv("ASSET_MANAGER_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("ASSET_MANAGER_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("ASSET_MANAGER_CORS_ORIGINS", '["http://localhost:5173"]')
    config = Settings(_env_file=None)
    assert config.database_path == tmp_path / "asset_prod.sqlite3"
    assert config.backup_dir == tmp_path / "backups"
    assert config.scheduler_enabled is False
    assert config.cors_origins == ["http://localhost:5173"]
    assert settings.database_path.name == "asset_dev.sqlite3"

    monkeypatch.setenv("ASSET_MANAGER_DATABASE_PATH", "/srv/runtime/data/asset_prod.sqlite3")
    monkeypatch.setenv("ASSET_MANAGER_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("ASSET_MANAGER_CORS_ORIGINS", "[]")
    container_config = Settings(_env_file=None)
    assert container_config.database_path == Path("/srv/runtime/data/asset_prod.sqlite3")
    assert container_config.scheduler_enabled is True
    assert container_config.cors_origins == []


def test_web_lifespan_does_not_create_database(tmp_path: Path, monkeypatch):
    from fastapi.testclient import TestClient

    sentinel = tmp_path / "never-created.sqlite3"
    monkeypatch.setattr(settings, "database_path", sentinel)
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    with pytest.raises(FileNotFoundError), TestClient(app):
        pass
    assert not sentinel.exists()


def test_scheduler_enabled_starts_once(monkeypatch, tmp_path: Path):
    from fastapi.testclient import TestClient
    import importlib

    main_module = importlib.import_module("app.main")

    class FakeScheduler:
        running = False
        starts = 0
        stops = 0

        def start(self):
            self.running = True
            self.starts += 1

        def shutdown(self, wait=False):
            self.running = False
            self.stops += 1

    fake = FakeScheduler()
    database = tmp_path / "scheduler.sqlite3"
    upgrade(database)
    monkeypatch.setattr(settings, "database_path", database)
    monkeypatch.setattr(main_module, "scheduler", fake)
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    with TestClient(app):
        assert fake.starts == 1
    assert fake.stops == 1
