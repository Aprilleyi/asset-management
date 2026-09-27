from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db.migrate import upgrade
from app.db.session import get_session
from app.main import app


@pytest.fixture()
def client(tmp_path: Path):
    database_path = tmp_path / "test.sqlite3"
    upgrade(database_path)
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    from app.core.config import settings

    original_backup_dir = settings.backup_dir
    original_database_path = settings.database_path
    original_upload_dir = settings.upload_dir
    original_ocr_cache_dir = settings.ocr_cache_dir
    original_scheduler_enabled = settings.scheduler_enabled
    original_seed = settings.seed_price_history_on_create
    settings.backup_dir = tmp_path / "backups"
    settings.database_path = database_path
    settings.upload_dir = tmp_path / "uploads"
    settings.ocr_cache_dir = tmp_path / "ocr-cache"
    settings.scheduler_enabled = False
    settings.seed_price_history_on_create = False

    with TestClient(app) as test_client:
        yield test_client, engine

    settings.backup_dir = original_backup_dir
    settings.database_path = original_database_path
    settings.upload_dir = original_upload_dir
    settings.ocr_cache_dir = original_ocr_cache_dir
    settings.scheduler_enabled = original_scheduler_enabled
    settings.seed_price_history_on_create = original_seed
    app.dependency_overrides.clear()
