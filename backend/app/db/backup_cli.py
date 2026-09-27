"""CLI for explicit backup and staged restore operations."""

import argparse
import json
from pathlib import Path

from app.core.config import settings
from app.db.sqlite_backup import create_verified_backup, restore_staged, verify_backup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--source", type=Path, required=True)
    backup.add_argument("--backup-dir", type=Path, required=True)
    backup.add_argument("--type", choices=["manual", "auto", "migration"], default="manual")
    restore = commands.add_parser("restore")
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)
    restore.add_argument("--promote", action="store_true")
    restore.add_argument("--replace-existing", action="store_true")
    restore.add_argument("--rollback-dir", type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "backup":
        path, manifest = create_verified_backup(args.source, args.backup_dir, args.type, settings.data_version)
        result = {"path": str(path), "manifest": manifest}
    elif args.command == "restore":
        path = restore_staged(args.backup, args.destination, args.promote, args.replace_existing, args.rollback_dir)
        result = {"path": str(path), "promoted": args.promote}
    else:
        result = {"manifest": verify_backup(args.backup)}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
