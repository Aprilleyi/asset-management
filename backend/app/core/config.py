from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Personal Asset Manager"
    data_version: str = "1.4.0"
    default_owner_id: str = "local_user"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    database_path: Path = Path(__file__).resolve().parents[3] / "data" / "asset_dev.sqlite3"
    backup_dir: Path = Path(__file__).resolve().parents[3] / "backups"
    upload_dir: Path = Path(__file__).resolve().parents[3] / "data" / "ocr_uploads"
    ocr_cache_dir: Path = Path(__file__).resolve().parents[3] / "data" / "paddleocr_home"
    scheduler_enabled: bool = True
    scheduler_timezone: str = "Asia/Shanghai"
    ocr_provider: str = "none"
    ocr_local_python_path: Optional[str] = None
    ocr_local_python_home: Optional[str] = None
    ocr_local_python_timeout_seconds: float = 120
    ocr_local_endpoints: list[str] = ["http://127.0.0.1:8866/ocr", "http://127.0.0.1:8001/ocr"]
    ocr_local_timeout_seconds: float = 1.5
    ocr_endpoint: Optional[str] = None
    ocr_api_key: Optional[str] = None
    ocr_model: Optional[str] = None
    ocr_timeout_seconds: float = 30
    seed_price_history_on_create: bool = True
    seed_price_history_days: int = 366

    model_config = SettingsConfigDict(env_file=".env", env_prefix="ASSET_MANAGER_", extra="ignore")

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"


settings = Settings()
