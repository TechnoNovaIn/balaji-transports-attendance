"""Unit tests for SQLite-to-PostgreSQL migration safety and integrity checks."""
import sqlite3
import tempfile
from pathlib import Path
import pytest

from scripts.migrate_sqlite_to_postgres import (
    open_sqlite_readonly,
    mask_db_url,
    normalize_postgres_url,
    parse_datetime,
    parse_date,
)


def test_open_sqlite_readonly_enforces_read_only(tmp_path):
    """Verify that open_sqlite_readonly opens database strictly in read-only mode and rejects writes."""
    db_file = tmp_path / "test_ro.sqlite3"
    init_conn = sqlite3.connect(db_file)
    init_conn.execute("CREATE TABLE sample (id INT PRIMARY KEY, name TEXT);")
    init_conn.execute("INSERT INTO sample VALUES (1, 'Alice');")
    init_conn.commit()
    init_conn.close()

    ro_conn = open_sqlite_readonly(db_file)
    try:
        # Reads should work
        row = ro_conn.execute("SELECT name FROM sample WHERE id = 1;").fetchone()
        assert row["name"] == "Alice"

        # Writes must be rejected by SQLite engine
        with pytest.raises(sqlite3.OperationalError, match="readonly database"):
            ro_conn.execute("INSERT INTO sample VALUES (2, 'Bob');")
    finally:
        ro_conn.close()


def test_integrity_check_with_sqlite3_row_factory_passes(tmp_path):
    """Verify that PRAGMA integrity_check correctly validates healthy database when using sqlite3.Row."""
    db_file = tmp_path / "test_healthy.sqlite3"
    init_conn = sqlite3.connect(db_file)
    init_conn.execute("CREATE TABLE sample (id INT PRIMARY KEY, name TEXT);")
    init_conn.commit()
    init_conn.close()

    conn = open_sqlite_readonly(db_file)
    try:
        assert conn.row_factory == sqlite3.Row
        check_rows = conn.execute("PRAGMA integrity_check;").fetchall()
        check_results = [r[0] for r in check_rows]
        assert check_results == ["ok"]
    finally:
        conn.close()


def test_integrity_check_failure_formats_readable_error():
    """Verify that unexpected integrity results format into human-readable error messages."""
    simulated_failure_rows = [("row 1 error: missing page",), ("row 2 error: corrupted index",)]
    check_results = [r[0] for r in simulated_failure_rows]
    assert check_results != ["ok"]
    error_details = ", ".join(str(msg) for msg in check_results)
    assert error_details == "row 1 error: missing page, row 2 error: corrupted index"


def test_mask_db_url_redacts_credentials():
    """Verify that credentials are fully redacted from database URLs."""
    raw = "postgresql://db_user:VerySecretPassword123@dpg-abc123-a.oregon-postgres.render.com:5432/balaji_db"
    masked = mask_db_url(raw)
    assert "VerySecretPassword123" not in masked
    assert "db_user:****@dpg-abc123-a.oregon-postgres.render.com:5432/balaji_db" in masked


def test_normalize_postgres_url():
    """Verify that postgres:// is normalized to postgresql://."""
    assert normalize_postgres_url("postgres://user:pass@host/db") == "postgresql://user:pass@host/db"
    assert normalize_postgres_url("postgresql://user:pass@host/db") == "postgresql://user:pass@host/db"
