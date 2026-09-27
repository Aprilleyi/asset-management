"""Compare two SQLite databases read-only, including every business row."""

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve(strict=True).as_uri() + "?mode=ro", uri=True)


def digest_rows(rows: list[tuple]) -> str:
    encoded = json.dumps(rows, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compare(source_path: Path, target_path: Path, expected_source_sha256: str, allow_alembic_stamp: bool = False) -> dict:
    if sha256(source_path) != expected_source_sha256:
        raise ValueError("Source SHA-256 changed before comparison")
    with closing(connect_readonly(source_path)) as source, closing(connect_readonly(target_path)) as target:
        for connection in (source, target):
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("SQLite integrity_check failed")

        def schema(connection):
            rows = connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL ORDER BY type, name"
            ).fetchall()
            if allow_alembic_stamp:
                rows = [row for row in rows if row[1] != "alembic_version"]
            return rows

        if schema(source) != schema(target):
            raise ValueError("Table, column, index, or SQL schema differs")
        table_names = [row[1] for row in schema(source) if row[0] == "table"]
        counts = {}
        digests = {}
        for name in table_names:
            quoted = name.replace('"', '""')
            sql = f'SELECT * FROM "{quoted}" ORDER BY id'
            source_rows = source.execute(sql).fetchall()
            target_rows = target.execute(sql).fetchall()
            if source_rows != target_rows:
                raise ValueError(f"Business rows differ in {name}")
            counts[name] = len(source_rows)
            digests[name] = digest_rows(source_rows)

        important = {
            "assetIdDigest": digest_rows(source.execute("SELECT id FROM assets ORDER BY id").fetchall()),
            "transactionIdDigest": digest_rows(source.execute("SELECT id FROM transactions ORDER BY id").fetchall()),
            "latestPriceDate": source.execute('SELECT MAX("priceDate") FROM price_records').fetchone()[0],
            "snapshotDateRange": source.execute('SELECT MIN("snapshotDate"), MAX("snapshotDate") FROM daily_snapshots').fetchone(),
            "settingsDigest": digests["settings"],
            "alertRulesDigest": digests["alert_rules"],
            "migrationHistoryDigest": digests["schema_migrations"],
        }
    if sha256(source_path) != expected_source_sha256:
        raise ValueError("Source SHA-256 changed during comparison")
    return {
        "sourceSha256": expected_source_sha256,
        "targetSha256": sha256(target_path),
        "sourceSizeBytes": source_path.stat().st_size,
        "targetSizeBytes": target_path.stat().st_size,
        "tableCounts": counts,
        "keyData": important,
        "schemaAndRowsEqual": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--allow-alembic-stamp", action="store_true")
    args = parser.parse_args()
    result = compare(args.source, args.target, args.expected_source_sha256, args.allow_alembic_stamp)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
