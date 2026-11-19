"""Atomic SQLite backup script for Balaji Transports.

Performs a consistent, transaction-safe online backup of the SQLite database
using the native SQLite Backup API. Can safely run while the application
and WSGI server are actively serving attendance requests.
"""
from datetime import datetime
import os
from pathlib import Path
import sqlite3
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app import app


def backup_database(destination_dir: str | None = None) -> Path:
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not db_uri.startswith("sqlite:///"):
        raise RuntimeError(f"Backup script is intended for SQLite databases. Configured URI: {db_uri}")

    raw_path = db_uri.replace("sqlite:///", "")
    src_path = Path(raw_path)
    if not src_path.is_absolute():
        src_path = (BASE_DIR / src_path).resolve()

    if not src_path.exists():
        raise FileNotFoundError(f"Source database file not found at: {src_path}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(destination_dir) if destination_dir else BASE_DIR / "backups" / f"db_backup_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    dst_path = out_dir / src_path.name

    print(f"Starting atomic SQLite online backup:")
    print(f"  Source:      {src_path}")
    print(f"  Destination: {dst_path}")

    src_conn = sqlite3.connect(src_path)
    dst_conn = sqlite3.connect(dst_path)
    try:
        with dst_conn:
            src_conn.backup(dst_conn, pages=100)
    finally:
        src_conn.close()
        dst_conn.close()

    # Verify backup integrity
    verify_conn = sqlite3.connect(dst_path)
    try:
        check = verify_conn.execute("PRAGMA integrity_check;").fetchall()
        if check != [("ok",)]:
            raise RuntimeError(f"Backup verification failed: {check}")
        user_count = verify_conn.execute("SELECT count(*) FROM users;").fetchone()[0]
        att_count = verify_conn.execute("SELECT count(*) FROM attendance;").fetchone()[0]
        print(f"  Integrity:   PASSED (ok)")
        print(f"  Verified:    {user_count} users, {att_count} attendance records.")
    finally:
        verify_conn.close()

    print(f"SUCCESS: Backup completed successfully at {dst_path}")
    return dst_path


if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else None
    backup_database(dest)
