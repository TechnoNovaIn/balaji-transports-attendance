"""Safe SQLite restoration script for Balaji Transports.

Validates the integrity of a backup file, safely stages a rollback copy of the
current database, and restores the database file into the active path.
"""
from datetime import datetime
from pathlib import Path
import shutil
import sqlite3
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app import app


def restore_database(backup_file_path: str) -> None:
    backup_path = Path(backup_file_path).resolve()
    if not backup_path.exists():
        print(f"ERROR: Backup file does not exist: {backup_path}")
        sys.exit(1)

    print(f"1. Validating backup file integrity...")
    test_conn = sqlite3.connect(backup_path)
    try:
        check = test_conn.execute("PRAGMA integrity_check;").fetchall()
        if check != [("ok",)]:
            print(f"ERROR: Backup file corrupted or invalid: {check}")
            sys.exit(1)
        users = test_conn.execute("SELECT count(*) FROM users;").fetchone()[0]
        attendance = test_conn.execute("SELECT count(*) FROM attendance;").fetchone()[0]
        print(f"   Integrity check: OK")
        print(f"   Found: {users} users, {attendance} attendance records.")
    finally:
        test_conn.close()

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not db_uri.startswith("sqlite:///"):
        raise RuntimeError(f"Configured database is not SQLite: {db_uri}")

    raw_dest = db_uri.replace("sqlite:///", "")
    target_path = Path(raw_dest)
    if not target_path.is_absolute():
        target_path = (BASE_DIR / target_path).resolve()

    target_path.parent.mkdir(parents=True, exist_ok=True)

    # 2. Stage safety snapshot of current database if one exists
    if target_path.exists():
        safety_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safety_path = target_path.parent / f"{target_path.stem}_pre_restore_{safety_ts}.sqlite3"
        print(f"2. Creating pre-restoration rollback snapshot of current database:")
        print(f"   {safety_path}")
        shutil.copy2(target_path, safety_path)

    # 3. Restore via atomic SQLite backup API to active database
    print(f"3. Restoring {backup_path.name} -> {target_path}...")
    src_conn = sqlite3.connect(backup_path)
    dst_conn = sqlite3.connect(target_path)
    try:
        with dst_conn:
            src_conn.backup(dst_conn)
    finally:
        src_conn.close()
        dst_conn.close()

    print(f"SUCCESS: Restoration complete. Active database now reflects backup from {backup_path}.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/restore_db.py <path_to_backup_sqlite3_file>")
        sys.exit(1)
    restore_database(sys.argv[1])
