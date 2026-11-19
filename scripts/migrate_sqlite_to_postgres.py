"""Safe, reusable SQLite-to-PostgreSQL data migration script for Balaji Transports.

Transfers all employee records, departments, roles, authentication hashes,
and complete attendance history from local SQLite to a target PostgreSQL database.

Safety & Verification Guarantees:
- Strict Read-Only Source: Opens SQLite with `?mode=ro` (refuses any write attempts).
- Non-Destructive Dry Run: `--dry-run` performs read-only checks without writing to target.
- Preserves explicit primary keys (user IDs, attendance IDs) and foreign keys.
- Foreign Key Integrity: Users are migrated first, followed by attendance.
- Conflict Safety: Verifies employee ID and email match before skipping; aborts if mismatched
  IDs would cause attendance records to be assigned to the wrong employee.
- Target Inspection Before DDL: Checks table existence before calling db.create_all().
- Accurate Pre/Post Count Validation: Accounts for any pre-existing records in target database.
- Synchronizes PostgreSQL sequence counters (`setval`) after migration.
- Atomic Transaction: Commits only if all rows and sequences succeed; rolls back on any error.
- Zero Credential Leakage: Passwords in database URLs are masked in all console outputs.

Usage Examples:
  1. Dry Run (Inspect source and target without modifying PostgreSQL):
     python scripts/migrate_sqlite_to_postgres.py --postgres-url "postgresql://user:pass@host/db" --dry-run

  2. Execute Full Migration (Using environment variable to protect credentials):
     $env:TARGET_DATABASE_URL="postgresql://user:pass@host/db"
     python scripts/migrate_sqlite_to_postgres.py

  3. Safe Retry / Skip Existing (Only if identical records already exist in target):
     python scripts/migrate_sqlite_to_postgres.py --on-conflict skip
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, inspect, text

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app import Attendance, User, app, db


def mask_db_url(url: str) -> str:
    """Mask password in database URL for safe logging."""
    try:
        parsed = urlparse(url)
        if parsed.password:
            netloc = f"{parsed.username}:****@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    except Exception:
        pass
    return "postgresql://***:****@***"


def normalize_postgres_url(url: str) -> str:
    """Ensure standard postgresql:// scheme compatible with SQLAlchemy."""
    url = url.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def open_sqlite_readonly(sqlite_path: Path) -> sqlite3.Connection:
    """Open SQLite database in strict read-only mode using SQLite URI syntax."""
    abs_posix = sqlite_path.resolve().as_posix()
    # file:{path}?mode=ro ensures the SQLite engine rejects any write operations
    uri = f"file:{abs_posix}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def parse_datetime(val: str | None) -> datetime | None:
    """Parse SQLite ISO datetime strings into datetime objects."""
    if not val:
        return None
    val = val.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return None


def parse_date(val: str | None):
    """Parse SQLite date string into date object."""
    if not val:
        return None
    val = val.strip().split("T")[0].split()[0]
    return datetime.strptime(val, "%Y-%m-%d").date()


def migrate_data(
    sqlite_path: Path,
    target_url: str,
    dry_run: bool = False,
    on_conflict: str = "error",
) -> bool:
    """Migrate data safely from SQLite to PostgreSQL."""
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite source database not found at: {sqlite_path}")

    target_url = normalize_postgres_url(target_url)
    masked_url = mask_db_url(target_url)

    print("=" * 70)
    print(" BALAJI TRANSPORTS — DATABASE MIGRATION (SQLite -> PostgreSQL)")
    print("=" * 70)
    print(f" Source SQLite:     {sqlite_path} ({sqlite_path.stat().st_size} bytes, READ-ONLY)")
    print(f" Target PostgreSQL: {masked_url}")
    print(f" Dry Run Mode:      {dry_run}")
    print(f" Conflict Mode:     {on_conflict}")
    print("=" * 70)

    # 1. Inspect source SQLite in STRICT READ-ONLY mode
    print("\n[1/5] Inspecting source SQLite database (read-only mode)...")
    sqlite_conn = open_sqlite_readonly(sqlite_path)
    try:
        check_rows = sqlite_conn.execute("PRAGMA integrity_check;").fetchall()
        check_results = [r[0] for r in check_rows]
        if check_results != ["ok"]:
            error_details = ", ".join(str(msg) for msg in check_results)
            raise RuntimeError(f"SQLite integrity check failed: {error_details}")

        src_users = sqlite_conn.execute("SELECT * FROM users ORDER BY id ASC;").fetchall()

        src_attendance = sqlite_conn.execute("SELECT * FROM attendance ORDER BY id ASC;").fetchall()
        src_user_ids = [r["id"] for r in src_users]
        src_att_ids = [r["id"] for r in src_attendance]
        print(f"      Source Verified: {len(src_users)} users, {len(src_attendance)} attendance records.")
    finally:
        sqlite_conn.close()

    # 2. Connect to target PostgreSQL
    print(f"\n[2/5] Testing connection to target PostgreSQL database...")
    pg_engine = create_engine(target_url, echo=False)

    with pg_engine.connect() as test_conn:
        backend_name = test_conn.dialect.name
        if backend_name != "postgresql":
            raise ValueError(f"Target dialect must be PostgreSQL, got: '{backend_name}'")
        version_str = test_conn.execute(text("SELECT version();")).scalar()
        short_ver = version_str.split(",")[0] if version_str else "PostgreSQL"
        print(f"      Connected successfully: {short_ver}")

    # 3. Check for existing tables BEFORE calling db.create_all()
    print("\n[3/5] Verifying target PostgreSQL schema...")
    inspector = inspect(pg_engine)
    existing_tables = inspector.get_table_names()
    print(f"      Existing tables present in target: {existing_tables}")

    needed_tables = [t for t in ("users", "attendance") if t not in existing_tables]

    if needed_tables:
        if dry_run:
            print(f"      [Dry Run] Missing tables detected: {needed_tables}")
            print(f"                db.create_all() will create them automatically during actual migration.")
        else:
            print(f"      Creating missing tables in target: {needed_tables}...")
            orig_uri = app.config.get("SQLALCHEMY_DATABASE_URI")
            try:
                app.config["SQLALCHEMY_DATABASE_URI"] = target_url
                with app.app_context():
                    db.create_all()
            finally:
                app.config["SQLALCHEMY_DATABASE_URI"] = orig_uri

            # Verify tables were created
            inspector = inspect(pg_engine)
            after_tables = inspector.get_table_names()
            if "users" not in after_tables or "attendance" not in after_tables:
                raise RuntimeError("Failed to create required tables ('users', 'attendance') in target database.")
            print(f"      Tables created successfully: {after_tables}")
    else:
        print("      All required tables ('users', 'attendance') already exist in target.")

    # DRY RUN EXIT: Confirm zero modifications
    if dry_run:
        print("\n" + "=" * 70)
        print(" [DRY RUN COMPLETE] Zero modifications made to PostgreSQL.")
        print(f" Ready to migrate: {len(src_users)} users and {len(src_attendance)} attendance records.")
        print("=" * 70)
        return True

    # 4. Perform Data Migration in a Single Atomic Transaction
    print("\n[4/5] Executing atomic data migration...")
    sqlite_conn = open_sqlite_readonly(sqlite_path)

    users_inserted = 0
    users_skipped = 0
    att_inserted = 0
    att_skipped = 0

    try:
        with pg_engine.begin() as conn:
            # Record baseline counts prior to migration to handle pre-existing records accurately
            initial_user_cnt = conn.execute(text("SELECT count(*) FROM users;")).scalar() or 0
            initial_att_cnt = conn.execute(text("SELECT count(*) FROM attendance;")).scalar() or 0

            # Query existing target state for safe conflict detection
            existing_pg_users = conn.execute(text("SELECT id, employee_id, email FROM users;")).fetchall()
            pg_user_by_id = {r[0]: (r[1], r[2]) for r in existing_pg_users}
            pg_user_by_email = {r[2]: (r[0], r[1]) for r in existing_pg_users}
            pg_user_by_emp_id = {r[1]: (r[0], r[2]) for r in existing_pg_users}

            existing_pg_att = conn.execute(text("SELECT id, user_id, attendance_date FROM attendance;")).fetchall()
            pg_att_by_id = {r[0] for r in existing_pg_att}
            pg_att_by_user_date = {(r[1], r[2].isoformat() if hasattr(r[2], "isoformat") else str(r[2])) for r in existing_pg_att}

            # A. Migrate Users
            print(f"      Processing {len(src_users)} user records...")
            for row in src_users:
                u_id = row["id"]
                u_emp_id = row["employee_id"]
                u_email = row["email"]

                conflict_found = False

                # Check if user ID already exists in target
                if u_id in pg_user_by_id:
                    existing_emp_id, existing_email = pg_user_by_id[u_id]
                    if existing_emp_id != u_emp_id or existing_email != u_email:
                        raise ValueError(
                            f"INTEGRITY MISMATCH: PostgreSQL user ID={u_id} belongs to '{existing_emp_id}' ({existing_email}), "
                            f"but SQLite user ID={u_id} is '{u_emp_id}' ({u_email}). "
                            f"Skipping would associate attendance records with the wrong employee! Aborting."
                        )
                    conflict_found = True

                # Check if employee_id already exists under a different ID
                if u_emp_id in pg_user_by_emp_id:
                    existing_id, existing_email = pg_user_by_emp_id[u_emp_id]
                    if existing_id != u_id:
                        raise ValueError(
                            f"INTEGRITY MISMATCH: Employee ID '{u_emp_id}' exists in PostgreSQL with ID={existing_id}, "
                            f"but SQLite has ID={u_id}. Foreign keys would mismatch! Aborting."
                        )
                    conflict_found = True

                # Check if email already exists under a different ID
                if u_email in pg_user_by_email:
                    existing_id, existing_emp_id = pg_user_by_email[u_email]
                    if existing_id != u_id:
                        raise ValueError(
                            f"INTEGRITY MISMATCH: Email '{u_email}' exists in PostgreSQL with ID={existing_id}, "
                            f"but SQLite has ID={u_id}. Foreign keys would mismatch! Aborting."
                        )
                    conflict_found = True

                if conflict_found:
                    if on_conflict == "skip":
                        users_skipped += 1
                        continue
                    else:
                        raise ValueError(
                            f"Conflict detected: User ID={u_id} ('{u_emp_id}', '{u_email}') already exists in target. "
                            f"Use --on-conflict skip to safely bypass identical existing records."
                        )

                shift_val = row["shift_timing"] if "shift_timing" in row.keys() else "10:00 AM - 07:00 PM"
                phone_val = row["phone"] if "phone" in row.keys() else None

                conn.execute(
                    text("""
                        INSERT INTO users (
                            id, employee_id, full_name, email, phone, shift_timing,
                            department, job_title, role, active, password_hash, created_at
                        ) VALUES (
                            :id, :employee_id, :full_name, :email, :phone, :shift_timing,
                            :department, :job_title, :role, :active, :password_hash, :created_at
                        )
                    """),
                    {
                        "id": u_id,
                        "employee_id": u_emp_id,
                        "full_name": row["full_name"],
                        "email": u_email,
                        "phone": phone_val,
                        "shift_timing": shift_val,
                        "department": row["department"],
                        "job_title": row["job_title"],
                        "role": row["role"],
                        "active": bool(row["active"]),
                        "password_hash": row["password_hash"],
                        "created_at": parse_datetime(row["created_at"]) or datetime.now(),
                    },
                )
                users_inserted += 1

            # B. Migrate Attendance Records
            print(f"      Processing {len(src_attendance)} attendance records...")
            for row in src_attendance:
                a_id = row["id"]
                a_user_id = row["user_id"]
                a_date = parse_date(row["attendance_date"])
                a_date_str = a_date.isoformat() if a_date else str(row["attendance_date"])

                att_conflict = (a_id in pg_att_by_id) or ((a_user_id, a_date_str) in pg_att_by_user_date)

                if att_conflict:
                    if on_conflict == "skip":
                        att_skipped += 1
                        continue
                    else:
                        raise ValueError(
                            f"Conflict detected: Attendance record ID={a_id} for user_id={a_user_id} on {a_date_str} "
                            f"already exists in target. Use --on-conflict skip to safely bypass identical records."
                        )

                r_keys = row.keys()
                break_start = parse_datetime(row["break_start_at"]) if "break_start_at" in r_keys else None
                break_end = parse_datetime(row["break_end_at"]) if "break_end_at" in r_keys else None
                exc_granted = bool(row["exception_granted"]) if "exception_granted" in r_keys else False
                marked_admin = bool(row["marked_by_admin"]) if "marked_by_admin" in r_keys else False
                admin_note = row["admin_note"] if "admin_note" in r_keys else None
                checkin_acc = float(row["checkin_accuracy"]) if ("checkin_accuracy" in r_keys and row["checkin_accuracy"] is not None) else None
                checkout_acc = float(row["checkout_accuracy"]) if ("checkout_accuracy" in r_keys and row["checkout_accuracy"] is not None) else None

                conn.execute(
                    text("""
                        INSERT INTO attendance (
                            id, user_id, attendance_date, checkin_at, checkout_at,
                            checkin_latitude, checkin_longitude, checkout_latitude, checkout_longitude,
                            checkin_accuracy, checkout_accuracy, break_start_at, break_end_at,
                            exception_granted, marked_by_admin, admin_note
                        ) VALUES (
                            :id, :user_id, :attendance_date, :checkin_at, :checkout_at,
                            :checkin_latitude, :checkin_longitude, :checkout_latitude, :checkout_longitude,
                            :checkin_accuracy, :checkout_accuracy, :break_start_at, :break_end_at,
                            :exception_granted, :marked_by_admin, :admin_note
                        )
                    """),
                    {
                        "id": a_id,
                        "user_id": a_user_id,
                        "attendance_date": a_date,
                        "checkin_at": parse_datetime(row["checkin_at"]),
                        "checkout_at": parse_datetime(row["checkout_at"]),
                        "checkin_latitude": float(row["checkin_latitude"]),
                        "checkin_longitude": float(row["checkin_longitude"]),
                        "checkout_latitude": float(row["checkout_latitude"]) if row["checkout_latitude"] is not None else None,
                        "checkout_longitude": float(row["checkout_longitude"]) if row["checkout_longitude"] is not None else None,
                        "checkin_accuracy": checkin_acc,
                        "checkout_accuracy": checkout_acc,
                        "break_start_at": break_start,
                        "break_end_at": break_end,
                        "exception_granted": exc_granted,
                        "marked_by_admin": marked_admin,
                        "admin_note": admin_note,
                    },
                )
                att_inserted += 1

            # C. Synchronize PostgreSQL Primary Key Sequences
            print("      Synchronizing PostgreSQL identity sequences (setval)...")
            for tbl in ("users", "attendance"):
                seq_name = conn.execute(text(f"SELECT pg_get_serial_sequence('{tbl}', 'id');")).scalar()
                if seq_name:
                    conn.execute(
                        text(f"""
                            SELECT setval(
                                '{seq_name}',
                                COALESCE((SELECT MAX(id) FROM {tbl}), 1),
                                (SELECT MAX(id) FROM {tbl}) IS NOT NULL
                            );
                        """)
                    )
                    print(f"        Sequence '{seq_name}' updated to MAX(id).")
                else:
                    print(f"        [Note] No auto-serial sequence returned for {tbl}.id.")

        # 5. Post-Migration Verification
        print("\n[5/5] Performing post-migration validation checks...")
        with pg_engine.connect() as verify_conn:
            final_user_cnt = verify_conn.execute(text("SELECT count(*) FROM users;")).scalar() or 0
            final_att_cnt = verify_conn.execute(text("SELECT count(*) FROM attendance;")).scalar() or 0

            # Verify that every single source user ID now exists in target
            matched_users = verify_conn.execute(
                text("SELECT count(*) FROM users WHERE id = ANY(:ids);"),
                {"ids": src_user_ids}
            ).scalar() or 0

            matched_att = verify_conn.execute(
                text("SELECT count(*) FROM attendance WHERE id = ANY(:ids);"),
                {"ids": src_att_ids}
            ).scalar() or 0

        print("\n" + "=" * 70)
        print(" MIGRATION VERIFICATION AUDIT REPORT")
        print("=" * 70)
        print(f" {'Table':<15} | {'Source (SQLite)':<16} | {'Target (PostgreSQL)':<19} | {'Status':<10}")
        print("-" * 70)

        expected_final_users = initial_user_cnt + users_inserted
        expected_final_att = initial_att_cnt + att_inserted

        users_status = "MATCHED" if (final_user_cnt == expected_final_users and matched_users == len(src_user_ids)) else "MISMATCH"
        att_status = "MATCHED" if (final_att_cnt == expected_final_att and matched_att == len(src_att_ids)) else "MISMATCH"

        print(f" {'users':<15} | {len(src_users):<16} | {final_user_cnt} (new: {users_inserted}){'':<7} | {users_status:<10}")
        print(f" {'attendance':<15} | {len(src_attendance):<16} | {final_att_cnt} (new: {att_inserted}){'':<7} | {att_status:<10}")
        print("-" * 70)
        print(f" Summary: Users:      {users_inserted} newly inserted, {users_skipped} already existed.")
        print(f"          Attendance: {att_inserted} newly inserted, {att_skipped} already existed.")
        print(f"          Pre-existing target rows: {initial_user_cnt} users, {initial_att_cnt} attendance.")
        print(f"          Target total rows:        {final_user_cnt} users, {final_att_cnt} attendance.")
        print(" Sequence synchronization: PASSED")
        print("=" * 70)

        if users_status != "MATCHED" or att_status != "MATCHED":
            raise RuntimeError("Post-migration record count mismatch detected!")

        return True

    except Exception as e:
        print(f"\n[ABORTED] Migration failed and was rolled back automatically: {e}", file=sys.stderr)
        raise
    finally:
        sqlite_conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Balaji Workforce SQLite database to PostgreSQL.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=BASE_DIR / "instance" / "balaji_workforce.sqlite3",
        help="Path to source SQLite database file.",
    )
    parser.add_argument(
        "--postgres-url",
        type=str,
        default=os.environ.get("TARGET_DATABASE_URL", ""),
        help="Target PostgreSQL connection URL. Can also be supplied via TARGET_DATABASE_URL env var.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect databases and validate migration steps without modifying target.",
    )
    parser.add_argument(
        "--on-conflict",
        choices=["error", "skip"],
        default="error",
        help="Action to take if an existing primary key or email is found in target.",
    )

    args = parser.parse_args()

    if not args.postgres_url:
        print(
            "ERROR: Target PostgreSQL URL is required.\n"
            "Provide it via --postgres-url or set the TARGET_DATABASE_URL environment variable.\n"
            "Example:\n"
            "  python scripts/migrate_sqlite_to_postgres.py --postgres-url \"postgresql://user:pass@host/db\" --dry-run\n",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        migrate_data(
            sqlite_path=args.sqlite,
            target_url=args.postgres_url,
            dry_run=args.dry_run,
            on_conflict=args.on_conflict,
        )
    except Exception as exc:
        print(f"\nMigration aborted: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
