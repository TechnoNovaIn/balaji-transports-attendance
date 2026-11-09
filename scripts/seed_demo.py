"""Seed fictional demo accounts and historical sample attendance.

Safe to run more than once. Existing employee accounts are not deleted.
Existing account enabled/disabled status and password are preserved.
"""
from datetime import datetime, time, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.exc import IntegrityError

from app import app, db, User, Attendance, now_ist

DEMO_PASSWORD = "DemoPass123!"  # Demo only; never use for real employee accounts.

# Latest factory coordinates supplied from Google Maps. These are used only
# to make fictional historical sample records appear near the demonstration site.
FACTORY_LATITUDE = 13.3698889
FACTORY_LONGITUDE = 77.1190278

# Demo admin and manager are assigned to valid company department names.
# Change these two demo assignments if the company wants different departments.
PEOPLE = [
    dict(
        employee_id="BW-1001",
        full_name="Dhyan",
        email="admin@balaji.demo",
        phone="9876500001",
        shift_timing="10:00 AM - 07:00 PM",
        department="Finance",
        job_title="System Administrator",
        role="admin",
    ),
    dict(
        employee_id="BW-1002",
        full_name="Rohan Shetty",
        email="manager@balaji.demo",
        phone="9876500002",
        shift_timing="10:00 AM - 07:00 PM",
        department="Tally",
        job_title="Department Manager",
        role="manager",
    ),
    dict(
        employee_id="BW-1003",
        full_name="Kiran Kumar",
        email="kiran@balaji.demo",
        phone="9876500003",
        shift_timing="10:00 AM - 07:00 PM",
        department="Tally",
        job_title="Tally",
        role="employee",
    ),
    dict(
        employee_id="BW-1004",
        full_name="Meera Nair",
        email="meera@balaji.demo",
        phone="9876500004",
        shift_timing="09:00 AM - 06:00 PM",
        department="AI",
        job_title="AI Specialist",
        role="employee",
    ),
    dict(
        employee_id="BW-1005",
        full_name="Arjun Patil",
        email="arjun@balaji.demo",
        phone="9876500005",
        shift_timing="08:00 AM - 05:00 PM",
        department="Accounts",
        job_title="Accounts",
        role="employee",
    ),
    dict(
        employee_id="BW-1006",
        full_name="Pooja Reddy",
        email="pooja@balaji.demo",
        phone="9876500006",
        shift_timing="10:00 AM - 07:00 PM",
        department="Billing",
        job_title="Billing",
        role="employee",
    ),
    dict(
        employee_id="BW-1008",
        full_name="Harsith",
        email="harsith@balaji.demo",
        phone="9876500008",
        shift_timing="02:00 PM - 11:00 PM",
        department="Tyre Department",
        job_title="Tyre Department",
        role="employee",
    ),
    dict(
        employee_id="BW-1009",
        full_name="Manjunath",
        email="manjunath@balaji.demo",
        phone="9876500009",
        shift_timing="10:00 AM - 07:00 PM",
        department="Inventory",
        job_title="Inventory",
        role="employee",
    ),
]


def validate_people_list() -> None:
    """Fail clearly if the PEOPLE list itself repeats an email or employee ID."""
    seen_employee_ids = set()
    seen_emails = set()

    for person in PEOPLE:
        employee_id = person["employee_id"].strip().upper()
        email = person["email"].strip().lower()

        if employee_id in seen_employee_ids:
            raise SystemExit(f"Duplicate employee_id in PEOPLE list: {employee_id}")
        if email in seen_emails:
            raise SystemExit(f"Duplicate email in PEOPLE list: {email}")

        seen_employee_ids.add(employee_id)
        seen_emails.add(email)


def demo_checkout_time(day_index: int, employee_index: int) -> time:
    """Return mostly on-time fictional checkout times; about 20% are Early."""
    early = (day_index + employee_index) % 5 == 0
    if early:
        return time(18, 40 + (employee_index % 15))  # 18:40–18:54, before 7 PM
    return time(19, (day_index * 3 + employee_index) % 16)  # 7:00–7:15 PM


with app.app_context():
    validate_people_list()
    db.create_all()

    # This map contains only demo accounts safely matched or created by this run.
    users = {}
    skipped_accounts = []

    for details in PEOPLE:
        email = details["email"].strip().lower()
        employee_id = details["employee_id"].strip().upper()

        # Look up both unique identifiers. This prevents a new demo account from
        # colliding with an existing employee that happens to use the same ID.
        user_by_email = User.query.filter_by(email=email).first()
        user_by_employee_id = User.query.filter_by(employee_id=employee_id).first()

        if (
            user_by_employee_id is not None
            and (user_by_email is None or user_by_employee_id.id != user_by_email.id)
        ):
            warning = (
                f"Skipped demo account {email}: employee ID {employee_id} "
                "already belongs to a different account."
            )
            print(f"WARNING: {warning}")
            skipped_accounts.append(email)
            continue

        if user_by_email is not None:
            user = user_by_email
            # Refresh the configured demo profile fields but preserve password
            # and active/inactive status so admin account management is respected.
            for key, value in details.items():
                setattr(user, key, value)
        else:
            user = User(**details, active=True)
            user.set_password(DEMO_PASSWORD)
            db.session.add(user)

        users[employee_id] = user

    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise SystemExit(
            "Could not save demo accounts because of a database uniqueness conflict. "
            "Check that employee IDs and emails are unique in the PEOPLE list and database."
        ) from exc

    # Seed only the demo employees that actually matched or were safely created.
    # This avoids KeyError when an ID is removed from PEOPLE or skipped due to a collision.
    demo_employee_ids = [
        person["employee_id"]
        for person in PEOPLE
        if person["role"] == "employee"
        and person["employee_id"] in users
        and users[person["employee_id"]].active
    ]

    # Historical sample attendance only; do not create a fictional record for today.
    today = now_ist().date()
    workdays = []
    day = today - timedelta(days=14)
    while day < today:
        if day.weekday() < 5:
            workdays.append(day)
        day += timedelta(days=1)

    inserted = 0
    updated_demo_checkouts = 0

    # Demo-only: update recent historical records belonging to @balaji.demo
    # accounts so most sample rows show On Time and a smaller portion show Early.
    # Today's records are deliberately untouched; a missing real checkout must
    # not be represented as On Time. This script is for the demo database only.
    demo_users_for_history = (
        User.query.filter(User.email.ilike("%@balaji.demo"))
        .order_by(User.employee_id.asc())
        .all()
    )
    history_employee_index = {user.id: index for index, user in enumerate(demo_users_for_history)}

    sample_days = workdays[-7:]
    for day_index, attendance_day in enumerate(sample_days):
        for user in demo_users_for_history:
            if user.id not in history_employee_index:
                continue
            existing_record = Attendance.query.filter_by(
                user_id=user.id,
                attendance_date=attendance_day,
            ).first()
            if existing_record is None:
                continue

            checkout_time = demo_checkout_time(
                day_index, history_employee_index[user.id]
            )
            existing_record.checkout_at = datetime.combine(
                attendance_day, checkout_time
            )
            updated_demo_checkouts += 1

    # Create missing historical sample records only for configured, active demo employees.
    for day_index, attendance_day in enumerate(sample_days):
        for index, employee_id in enumerate(demo_employee_ids):
            # Vary omissions so charts don't look artificially uniform.
            if (day_index + index) % 7 == 0:
                continue

            user = users[employee_id]
            existing_record = Attendance.query.filter_by(
                user_id=user.id,
                attendance_date=attendance_day,
            ).first()
            if existing_record:
                continue

            late = (day_index + index) % 4 == 0
            checkin_time = time(10, 20) if late else time(10, 0)
            checkin_at = datetime.combine(attendance_day, checkin_time)
            checkout_at = datetime.combine(
                attendance_day, demo_checkout_time(day_index, index)
            )

            # Slight offsets are fictional sample locations around the configured factory.
            latitude = FACTORY_LATITUDE + (index * 0.00005)
            longitude = FACTORY_LONGITUDE + (index * 0.00005)

            row = Attendance(
                user_id=user.id,
                attendance_date=attendance_day,
                checkin_at=checkin_at,
                checkout_at=checkout_at,
                checkin_latitude=latitude,
                checkin_longitude=longitude,
                checkout_latitude=latitude + 0.00002,
                checkout_longitude=longitude + 0.00002,
            )
            db.session.add(row)
            inserted += 1

    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise SystemExit(
            "Could not save sample attendance because of a duplicate employee/date record. "
            "No existing attendance records were intentionally deleted."
        ) from exc

    print(
        f"Demo seed complete. {len(users)} demo accounts matched or created; "
        f"{inserted} historical sample attendance rows added; "
        f"{updated_demo_checkouts} historical demo checkout times refreshed."
    )
    if skipped_accounts:
        print("Skipped demo accounts due to employee ID conflicts:")
        for email in skipped_accounts:
            print(f"  {email}")
    print("Local demo password for newly created demo accounts: DemoPass123!")
    print("Demo accounts in configured PEOPLE list:")
    for person in PEOPLE:
        if person["employee_id"] in users:
            print(f"  {person['role']:<8} {person['email']} ({person['department']})")
