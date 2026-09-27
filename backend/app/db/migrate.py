"""Explicit migration CLI: upgrade empty DBs, baseline verified existing DBs."""

import argparse
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.db.sqlite_backup import database_facts
from migrations.versions.schema_1_4_0 import BASELINE_SQL


HISTORY = {"1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0"}


def _configuration(database: Path) -> Config:
    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.resolve()}")
    return config


def _signature(connection: sqlite3.Connection) -> dict[str, tuple[tuple[str, ...], tuple[str, ...]]]:
    tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'")]
    result = {}
    for table in tables:
        columns = tuple(row[1] for row in connection.execute(f'PRAGMA table_info("{table}")'))
        indexes = tuple(sorted(row[1] for row in connection.execute(f'PRAGMA index_list("{table}")')))
        result[table] = (columns, indexes)
    return result


def validate_baseline(database: Path) -> None:
    if not database.is_file():
        raise FileNotFoundError(database)
    database_facts(database)
    with sqlite3.connect(":memory:") as expected, sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as actual:
        expected.executescript(BASELINE_SQL)
        if _signature(actual) != _signature(expected):
            raise ValueError("Existing schema differs from the frozen 1.4.0 baseline")
        versions = {row[0] for row in actual.execute("SELECT version FROM schema_migrations")}
        if versions != HISTORY:
            raise ValueError("Existing schema_migrations history differs from 1.0.0–1.4.0")


def baseline(database: Path) -> None:
    validate_baseline(database)
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'").fetchone():
            raise ValueError("Database is already managed by Alembic")
    command.stamp(_configuration(database), "head")


def upgrade(database: Path) -> None:
    if database.exists():
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            existing = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()
            versioned = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'").fetchone()
            if existing and not versioned:
                raise ValueError("Existing database requires verified baseline before upgrade")
    else:
        database.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(_configuration(database), "head")


def status(database: Path) -> None:
    managed(database)
    heads = ScriptDirectory.from_config(_configuration(database)).get_heads()
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        versions = [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
    if sorted(versions) != sorted(heads):
        raise ValueError(f"Pending Alembic migrations: current={versions}, heads={heads}")


def managed(database: Path) -> None:
    database_facts(database)
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        try:
            versions = [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
        except sqlite3.OperationalError as exc:
            raise ValueError("Alembic baseline has not been applied") from exc
    script = ScriptDirectory.from_config(_configuration(database))
    if not versions or any(script.get_revision(revision) is None for revision in versions):
        raise ValueError(f"Unknown Alembic revision: {versions}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["validate-baseline", "baseline", "upgrade", "managed", "status"])
    parser.add_argument("--database", required=True, type=Path)
    args = parser.parse_args()
    if args.action == "validate-baseline":
        validate_baseline(args.database)
    elif args.action == "baseline":
        baseline(args.database)
    elif args.action == "status":
        status(args.database)
    elif args.action == "managed":
        managed(args.database)
    else:
        upgrade(args.database)
    print(f"{args.action} succeeded: {args.database}")


if __name__ == "__main__":
    main()
