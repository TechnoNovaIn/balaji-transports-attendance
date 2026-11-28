import os
import sys
import tempfile
from datetime import datetime, time
from pathlib import Path

# Ensure project root is in sys.path when running tests directly with `python tests/test_app.py`
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Set the database URI before importing the global Flask app so tests never touch demo data.
_TEST_DB = os.path.join(tempfile.gettempdir(), "balaji_workforce_test_suite.sqlite3")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"

import pytest
from app import app, db, User, Attendance, now_ist, attendance_export_values, attendance_for_dashboard


@pytest.fixture(autouse=True)
def clean_database():
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        GEOFENCE_LATITUDE="12.9700",
        GEOFENCE_LONGITUDE="77.5900",
        GEOFENCE_RADIUS_METERS="1000",
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
        admin = make_user("BW-A001", "Administrator", "admin@test.local", "Administration", "admin")
        manager = make_user("BW-M001", "Manager One", "manager@test.local", "Operations", "manager")
        employee = make_user("BW-E001", "Employee One", "employee@test.local", "Operations", "employee")
        other = make_user("BW-E002", "Employee Two", "other@test.local", "Fleet", "employee")
        db.session.add_all([admin, manager, employee, other])
        db.session.commit()
    yield
    with app.app_context():
        db.session.remove()
        db.drop_all()


def make_user(employee_id, name, email, department, role):
    user = User(employee_id=employee_id, full_name=name, email=email, department=department,
                job_title="Test Role", role=role, active=True)
    user.set_password("TestPass123!")
    return user


def login(client, identifier, password="TestPass123!"):
    if "@" in identifier:
        return client.post("/login", data={"email": identifier, "password": password}, follow_redirects=True)
    return client.post("/employee-login", data={"identifier": identifier, "password": password}, follow_redirects=True)


def get_user(email):
    return User.query.filter_by(email=email).first()


def test_password_is_hashed_and_login_works():
    client = app.test_client()
    with app.app_context():
        user = get_user("admin@test.local")
        assert user.password_hash != "TestPass123!"
        assert user.check_password("TestPass123!")
        assert not user.check_password("wrong-password")
    response = login(client, "admin@test.local")
    assert response.status_code == 200
    assert b"Overview" in response.data




def test_universal_login_portal_supports_all_roles_and_identifiers():
    # Login page is universal and does not display role separation (no Admin vs Employee distinctions)
    login_page = app.test_client().get("/login")
    assert login_page.status_code == 200
    assert b"Admin / Manager" not in login_page.data
    assert b"Employee Login" not in login_page.data

    # Admin signs in via work email / Gmail on universal /login
    admin_attempt = app.test_client().post(
        "/login", data={"identifier": "admin@test.local", "password": "TestPass123!"}, follow_redirects=True
    )
    assert admin_attempt.status_code == 200
    assert b"Overview" in admin_attempt.data

    # Manager signs in via work email / Gmail on universal /login
    manager_attempt = app.test_client().post(
        "/login", data={"identifier": "manager@test.local", "password": "TestPass123!"}, follow_redirects=True
    )
    assert manager_attempt.status_code == 200
    assert b"Overview" in manager_attempt.data

    # Employee signs in via full name on universal /login
    employee_name_attempt = app.test_client().post(
        "/login", data={"identifier": "Employee One", "password": "TestPass123!"}, follow_redirects=True
    )
    assert employee_name_attempt.status_code == 200
    assert b"Today" in employee_name_attempt.data

    # Employee signs in via employee login ID on universal /login
    employee_id_attempt = app.test_client().post(
        "/login", data={"identifier": "BW-E001", "password": "TestPass123!"}, follow_redirects=True
    )
    assert employee_id_attempt.status_code == 200
    assert b"Today" in employee_id_attempt.data

    # Invalid password fails
    bad_attempt = app.test_client().post(
        "/login", data={"identifier": "Employee One", "password": "wrong-password"}, follow_redirects=True
    )
    assert b"Invalid credentials" in bad_attempt.data


def test_active_employee_full_names_must_be_unique():
    admin_client = app.test_client()
    login(admin_client, "admin@test.local")
    response = admin_client.post(
        "/employees/new",
        data={
            "full_name": "Employee One",
            "department": "Inventory",
            "job_title": "Store Assistant",
            "role": "employee",
            "password": "TempPass123!",
            "employee_id": "",
            "email": "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"full name" in response.data.lower()
    with app.app_context():
        assert User.query.filter_by(full_name="Employee One").count() == 1


def test_admin_and_manager_accounts_require_email():
    admin_client = app.test_client()
    login(admin_client, "admin@test.local")
    response = admin_client.post(
        "/employees/new",
        data={
            "full_name": "New Manager",
            "department": "Operations",
            "job_title": "Manager",
            "role": "manager",
            "password": "TempPass123!",
            "employee_id": "",
            "email": "",
        },
        follow_redirects=True,
    )
    assert b"work email is required" in response.data.lower()
    with app.app_context():
        assert User.query.filter_by(full_name="New Manager").first() is None


def test_unauthenticated_pages_redirect_to_login():
    response = app.test_client().get("/employees")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_can_open_employee_creation_but_manager_cannot():
    client = app.test_client()
    login(client, "admin@test.local")
    assert client.get("/employees/new").status_code == 200
    client.post("/logout")
    login(client, "manager@test.local")
    assert client.get("/employees/new").status_code == 403


def test_employee_cannot_open_employee_directory():
    client = app.test_client()
    login(client, "Employee One")
    assert client.get("/employees").status_code == 403


def test_manager_employee_scope_is_branch_limited():
    with app.app_context():
        emp2 = get_user("other@test.local")
        emp2.branch = "Bangalore (Whitefield)"
        db.session.commit()
    client = app.test_client()
    login(client, "manager@test.local")
    response = client.get("/employees")
    assert b"Employee One" in response.data
    assert b"Employee Two" not in response.data


def test_employee_cannot_view_another_employees_attendance():
    with app.app_context():
        employee = get_user("employee@test.local")
        other = get_user("other@test.local")
        today = now_ist().date()
        db.session.add(Attendance(user_id=other.id, attendance_date=today, checkin_at=datetime.combine(today, time(8, 50)),
                                  checkin_latitude=12.97, checkin_longitude=77.59))
        db.session.commit()
    client = app.test_client()
    login(client, "Employee One")
    response = client.get("/records?employee=4")
    assert response.status_code == 200
    assert b"Employee Two" not in response.data




def test_employee_dashboard_metrics_use_only_their_own_attendance():
    with app.app_context():
        employee = get_user("employee@test.local")
        other = get_user("other@test.local")
        today = now_ist().date()
        db.session.add_all([
            Attendance(
                user_id=employee.id,
                attendance_date=today,
                checkin_at=datetime.combine(today, time(10, 0)),
                checkin_latitude=12.97,
                checkin_longitude=77.59,
            ),
            Attendance(
                user_id=other.id,
                attendance_date=today,
                checkin_at=datetime.combine(today, time(10, 2)),
                checkin_latitude=12.97,
                checkin_longitude=77.59,
            ),
        ])
        db.session.commit()

    client = app.test_client()
    login(client, "Employee One")
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"Employee One" in response.data
    assert b"Employee Two" not in response.data

def test_checkin_requires_valid_coordinates_and_prevents_duplicates():
    client = app.test_client()
    login(client, "Employee One")
    invalid = client.post("/api/attendance/check-in", json={"latitude": 120, "longitude": 77.5})
    assert invalid.status_code == 400
    first = client.post("/api/attendance/check-in", json={"latitude": 12.9716, "longitude": 77.5946})
    assert first.status_code == 201
    second = client.post("/api/attendance/check-in", json={"latitude": 12.9716, "longitude": 77.5946})
    assert second.status_code == 409
    with app.app_context():
        user = get_user("employee@test.local")
        rows = Attendance.query.filter_by(user_id=user.id, attendance_date=now_ist().date()).all()
        assert len(rows) == 1


def test_checkout_requires_checkin_then_completes_record():
    client = app.test_client()
    login(client, "Employee One")
    missing = client.post("/api/attendance/check-out", json={"latitude": 12.97, "longitude": 77.59})
    assert missing.status_code == 409
    started = client.post("/api/attendance/check-in", json={"latitude": 12.97, "longitude": 77.59})
    assert started.status_code == 201
    ended = client.post("/api/attendance/check-out", json={"latitude": 12.9701, "longitude": 77.5901})
    assert ended.status_code == 200
    with app.app_context():
        record = Attendance.query.filter_by(user_id=get_user("employee@test.local").id, attendance_date=now_ist().date()).first()
        assert record.checkout_at is not None
        assert record.checkout_latitude == pytest.approx(12.9701)


def test_csv_report_contains_headers_and_attendance():
    with app.app_context():
        employee = get_user("employee@test.local")
        day = now_ist().date()
        db.session.add(Attendance(user_id=employee.id, attendance_date=day, checkin_at=datetime.combine(day, time(8, 55)),
                                  checkin_latitude=12.97, checkin_longitude=77.59))
        db.session.commit()
    client = app.test_client()
    login(client, "admin@test.local")
    response = client.get(f"/reports.csv?start={now_ist().date().isoformat()}&end={now_ist().date().isoformat()}")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/csv")
    assert b"Date,Employee Name,Branch,Department,Role,Login Status,Login Time,Logout Time,Logout Status" in response.data
    assert b"Employee One" in response.data
    assert b"10:00 AM" in response.data
    assert b"Normal" in response.data


def test_deactivated_users_cannot_login():
    with app.app_context():
        user = get_user("employee@test.local")
        user.active = False
        db.session.commit()
    response = login(app.test_client(), "Employee One")
    assert b"incorrect" in response.data.lower() or b"inactive" in response.data.lower()


def test_checkin_rejected_outside_factory_geofence():
    client = app.test_client()
    login(client, "Employee One")
    outside = client.post("/api/attendance/check-in", json={"latitude": 13.5, "longitude": 77.59})
    assert outside.status_code == 403
    assert b"outside the approved factory perimeter" in outside.data.lower()
    with app.app_context():
        assert Attendance.query.filter_by(user_id=get_user("employee@test.local").id, attendance_date=now_ist().date()).first() is None


def test_checkout_rejected_outside_factory_geofence():
    client = app.test_client()
    login(client, "Employee One")
    started = client.post("/api/attendance/check-in", json={"latitude": 12.9700, "longitude": 77.5900})
    assert started.status_code == 201
    ended = client.post("/api/attendance/check-out", json={"latitude": 13.5, "longitude": 77.59})
    assert ended.status_code == 403
    with app.app_context():
        record = Attendance.query.filter_by(user_id=get_user("employee@test.local").id, attendance_date=now_ist().date()).first()
        assert record is not None and record.checkout_at is None


def test_attendance_fails_closed_when_factory_geofence_is_not_configured():
    app.config.update(GEOFENCE_LATITUDE="", GEOFENCE_LONGITUDE="")
    client = app.test_client()
    login(client, "Employee One")
    response = client.post("/api/attendance/check-in", json={"latitude": 12.9700, "longitude": 77.5900})
    assert response.status_code == 503
    assert b"geofencing is not configured" in response.data.lower()


def test_admin_can_view_disabled_accounts_and_reactivate_them():
    with app.app_context():
        other = get_user("other@test.local")
        other.active = False
        db.session.commit()
        other_id = other.id
    client = app.test_client()
    login(client, "admin@test.local")
    disabled_page = client.get("/employees?status=disabled")
    assert disabled_page.status_code == 200
    assert b"Employee Two" in disabled_page.data
    response = client.post(f"/employees/{other_id}/activate?status=disabled", data={"csrf_token": "test"}, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(User, other_id).active is True


def test_admin_can_disable_employee_and_filter_status():
    with app.app_context():
        other = get_user("other@test.local")
        other_id = other.id
    client = app.test_client()
    login(client, "admin@test.local")
    response = client.post(f"/employees/{other_id}/deactivate?status=all", data={"csrf_token": "test"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Disabled" in response.data
    with app.app_context():
        assert db.session.get(User, other_id).active is False


def test_admin_is_also_rejected_outside_factory_geofence():
    client = app.test_client()
    login(client, "admin@test.local")
    response = client.post("/api/attendance/check-in", json={"latitude": 13.5, "longitude": 77.59})
    assert response.status_code == 403
    assert b"outside the approved factory perimeter" in response.data.lower()


def test_grace_period_status_is_normal_through_1015():
    day = now_ist().date()
    at_1015 = Attendance(attendance_date=day, checkin_at=datetime.combine(day, time(10, 15)),
                        checkin_latitude=12.97, checkin_longitude=77.59)
    at_1016 = Attendance(attendance_date=day, checkin_at=datetime.combine(day, time(10, 16)),
                        checkin_latitude=12.97, checkin_longitude=77.59)
    assert at_1015.status == "Present"
    assert at_1016.status == "Late"


def test_export_values_credit_early_login_and_flag_early_logout():
    day = now_ist().date()
    user = User(employee_id="BW-T100", full_name="Export Test", email="export@test.local",
                department="Accounts", job_title="Tester", role="employee", active=True)
    user.set_password("TestPass123!")
    record = Attendance(user=user, attendance_date=day,
                        checkin_at=datetime.combine(day, time(9, 50)),
                        checkout_at=datetime.combine(day, time(18, 59)),
                        checkin_latitude=12.97, checkin_longitude=77.59)
    login_time, login_status, logout_status = attendance_export_values(record)
    assert login_time.time() == time(10, 0)
    assert login_status == "Normal"
    assert logout_status == "Early"

    record.checkout_at = datetime.combine(day, time(19, 0))
    assert attendance_export_values(record)[2] == "On Time"
    record.checkout_at = None
    assert attendance_export_values(record)[2] == ""


def test_xlsx_report_download_returns_excel_content_type():
    client = app.test_client()
    login(client, "admin@test.local")
    response = client.get("/reports.xlsx")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.data[:2] == b"PK"


def test_employee_can_be_created_without_employee_id_or_email_and_login_with_full_name():
    admin_client = app.test_client()
    login(admin_client, "admin@test.local")
    response = admin_client.post(
        "/employees/new",
        data={
            "full_name": "No Email Employee",
            "department": "Inventory",
            "job_title": "Warehouse Assistant",
            "role": "employee",
            "password": "TempPass123!",
            "employee_id": "",
            "email": "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"employee login id" in response.data.lower() and b"employee login" in response.data.lower()
    with app.app_context():
        user = User.query.filter_by(full_name="No Email Employee").first()
        assert user is not None
        assert user.employee_id.startswith("SYS-")
        assert user.email.endswith("@no-email.invalid")
        system_id = user.employee_id
        placeholder_email = user.email

    employee_client = app.test_client()
    response = login(employee_client, "No Email Employee", "TempPass123!")
    assert response.status_code == 200
    assert b"Overview" in response.data

    # Employees must not use the management login with placeholder email. They may use their generated ID.
    email_attempt = app.test_client().post(
        "/login", data={"email": placeholder_email, "password": "TempPass123!"}, follow_redirects=True
    )
    assert b"Overview" not in email_attempt.data
    id_attempt = login(app.test_client(), system_id, "TempPass123!")
    assert b"Overview" in id_attempt.data


def test_employee_creation_form_marks_only_id_and_email_optional():
    client = app.test_client()
    login(client, "admin@test.local")
    response = client.get("/employees/new")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    employee_id_field = html.split('id="employee_id"', 1)[1].split(">", 1)[0]
    email_field = html.split('id="email"', 1)[1].split(">", 1)[0]
    job_title_field = html.split('id="job_title"', 1)[1].split(">", 1)[0]
    assert "required" not in employee_id_field
    assert "readonly" in employee_id_field
    assert "required" not in email_field
    assert "required" not in job_title_field
    for field in ("full_name", "department", "role", "password"):
        field_html = html.split(f'id="{field}"', 1)[1].split(">", 1)[0]
        assert "required" in field_html


def test_login_pages_explain_separate_role_specific_identifiers():
    login_page = app.test_client().get("/login")
    assert login_page.status_code == 200
    assert b"Admin / Manager" not in login_page.data
    assert b"Employee Login" not in login_page.data
    assert b"WORKFORCE PORTAL" in login_page.data
    employee_redirect = app.test_client().get("/employee-login")
    assert employee_redirect.status_code in {200, 302}


def test_employee_creation_rejects_missing_required_access_role():
    client = app.test_client()
    login(client, "admin@test.local")
    response = client.post(
        "/employees/new",
        data={
            "full_name": "Role Missing Person",
            "department": "Inventory",
            "job_title": "Store Assistant",
            "password": "TempPass123!",
            "employee_id": "",
            "email": "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"access role" in response.data.lower()
    with app.app_context():
        assert User.query.filter_by(full_name="Role Missing Person").first() is None


def test_employee_creation_rejects_missing_password():
    client = app.test_client()
    login(client, "admin@test.local")
    response = client.post(
        "/employees/new",
        data={
            "full_name": "Password Missing Person",
            "department": "Inventory",
            "job_title": "Store Assistant",
            "role": "employee",
            "employee_id": "",
            "email": "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"password" in response.data.lower()
    with app.app_context():
        assert User.query.filter_by(full_name="Password Missing Person").first() is None


def _previous_weekday():
    from datetime import timedelta
    day = now_ist().date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def test_daily_owner_report_shows_login_logout_and_absence_statuses():
    report_day = _previous_weekday()
    with app.app_context():
        employee = get_user("employee@test.local")
        db.session.add(Attendance(
            user_id=employee.id,
            attendance_date=report_day,
            checkin_at=datetime.combine(report_day, time(10, 5)),
            checkout_at=None,
            checkin_latitude=12.97,
            checkin_longitude=77.59,
        ))
        db.session.commit()

    client = app.test_client()
    login(client, "admin@test.local")
    response = client.get(f"/reports/daily?date={report_day.isoformat()}")
    assert response.status_code == 200
    assert b"Employee One" in response.data
    assert b"Normal" in response.data
    assert b"Pending" in response.data
    assert b"Employee Two" in response.data
    assert b"Absent" in response.data

    csv_response = client.get(f"/reports/daily.csv?date={report_day.isoformat()}")
    assert csv_response.status_code == 200
    assert csv_response.headers["Content-Type"].startswith("text/csv")
    assert b"Employee Name,Branch,Login Status,Logout Status" in csv_response.data
    assert b"Employee Two" in csv_response.data
    assert b"Absent" in csv_response.data
    assert b"Login Time" not in csv_response.data
    assert b"Logout Time" not in csv_response.data
    assert b"<th>Login time</th>" not in response.data
    assert b"<th>Logout time</th>" not in response.data


def test_daily_owner_report_is_admin_only():
    client = app.test_client()
    login(client, "Employee One")
    assert client.get("/reports/daily").status_code == 403
    assert client.get("/reports/daily.csv").status_code == 403


def test_employee_creation_with_phone_optional_job_title_auto_id_and_shift_timing():
    admin_client = app.test_client()
    login(admin_client, "admin@test.local")
    response = admin_client.post(
        "/employees/new",
        data={
            "full_name": "Phone And Shift Employee",
            "department": "Accounts",
            "job_title": "",  # Optional!
            "phone": "9876543210",
            "shift_timing": "09:00 AM - 06:00 PM",
            "role": "employee",
            "password": "TempPass123!",
            "employee_id": "(Auto-generated on save)",
            "email": "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(full_name="Phone And Shift Employee").first()
        assert user is not None
        assert user.employee_id.startswith("SYS-")
        assert user.phone == "9876543210"
        assert user.shift_timing == "09:00 AM - 06:00 PM"
        assert user.job_title == "Employee"

    # Employee can sign in using their phone number!
    emp_client = app.test_client()
    login_resp = emp_client.post("/employee-login", data={"identifier": "9876543210", "password": "TempPass123!"}, follow_redirects=True)
    assert login_resp.status_code == 200
    assert b"Phone And Shift Employee" in login_resp.data
    # Employee page shows their shift timing and attendance action
    assert b"09:00 AM - 06:00 PM" in login_resp.data
    assert b"Check in with GPS" in login_resp.data
    # Employee page does NOT show admin analytics / KPI grid / trend charts
    assert b"Attendance trend" not in login_resp.data
    assert b"Today's distribution" not in login_resp.data
    assert b"Active employees" not in login_resp.data


def test_break_buffer_start_end_and_display():
    client = app.test_client()
    login(client, "Employee One")
    today = now_ist().date()
    with app.app_context():
        user = get_user("employee@test.local")
        rec = Attendance.query.filter_by(user_id=user.id, attendance_date=today).first()
        if not rec:
            rec = Attendance(user_id=user.id, attendance_date=today, checkin_at=datetime.combine(today, time(9, 58)),
                             checkin_latitude=12.9716, checkin_longitude=77.5946)
            db.session.add(rec)
        else:
            rec.checkout_at = None
            rec.break_start_at = None
            rec.break_end_at = None
        db.session.commit()

    # Start break
    b_start = client.post("/api/attendance/break-start")
    assert b_start.status_code == 200
    assert b"1-hour break started" in b_start.data

    # End break
    b_end = client.post("/api/attendance/break-end")
    assert b_end.status_code == 200
    assert b"Break ended" in b_end.data

    # Check dashboard / attendance shows break was taken
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"1-hr Break" in resp.data
    assert b"Break (1h)" in resp.data


def test_multiple_breaks_accumulate_total_time():
    """Verify taking multiple breaks (e.g. 23m + 3m) accumulates to 26m total rather than overwriting."""
    client = app.test_client()
    login(client, "Employee One")
    today = now_ist().date()
    with app.app_context():
        user = get_user("employee@test.local")
        rec = Attendance.query.filter_by(user_id=user.id, attendance_date=today).first()
        if not rec:
            rec = Attendance(
                user_id=user.id,
                attendance_date=today,
                checkin_at=datetime.combine(today, time(9, 30)),
                checkin_latitude=12.9716,
                checkin_longitude=77.5946,
            )
            db.session.add(rec)
        else:
            rec.checkin_at = datetime.combine(today, time(9, 30))
            rec.checkout_at = None
            rec.break_start_at = None
            rec.break_end_at = None
            rec.total_break_seconds = 0
        db.session.commit()

    # 1. First break: 23 minutes (12:00 PM to 12:23 PM)
    with app.app_context():
        user = get_user("employee@test.local")
        rec = Attendance.query.filter_by(user_id=user.id, attendance_date=today).first()
        b1_start = datetime.combine(today, time(12, 0))
        b1_end = datetime.combine(today, time(12, 23))
        rec.break_start_at = b1_start
        rec.break_end_at = b1_end
        rec.total_break_seconds = int((b1_end - b1_start).total_seconds())  # 23 * 60 = 1380
        db.session.commit()

    # 2. Second break: start break at 01:00 PM
    with app.app_context():
        user = get_user("employee@test.local")
        rec = Attendance.query.filter_by(user_id=user.id, attendance_date=today).first()
        b2_start = datetime.combine(today, time(13, 0))
        rec.break_start_at = b2_start
        rec.break_end_at = None
        db.session.commit()

    # Verify break in progress recognizes previous break
    with app.app_context():
        user = get_user("employee@test.local")
        rec = Attendance.query.filter_by(user_id=user.id, attendance_date=today).first()
        assert rec.break_in_progress is True
        assert "23m taken earlier" in rec.break_display

    # End second break at 01:03 PM (3 minutes later)
    with app.app_context():
        user = get_user("employee@test.local")
        rec = Attendance.query.filter_by(user_id=user.id, attendance_date=today).first()
        b2_end = datetime.combine(today, time(13, 3))
        delta_sec = int((b2_end - rec.break_start_at).total_seconds())  # 180 seconds
        rec.total_break_seconds += delta_sec
        rec.break_end_at = b2_end
        db.session.commit()

    # Verify total accumulated break time is 26 minutes (1560s)
    with app.app_context():
        user = get_user("employee@test.local")
        rec = Attendance.query.filter_by(user_id=user.id, attendance_date=today).first()
        assert rec.total_break_seconds == 26 * 60
        assert "26m total" in rec.break_display

        # Test shift duration deduction with checkout at 06:30 PM (9 hours gross)
        rec.checkout_at = datetime.combine(today, time(18, 30))
        # Gross = 9 hours (540m). Net = 540m - 26m = 514m = 8h 34m
        assert rec.duration_display == "8h 34m"


def test_fifteen_minute_late_exception_buffer():
    today = now_ist().date()
    with app.app_context():
        user = get_user("employee@test.local")
        rec = Attendance.query.filter_by(user_id=user.id, attendance_date=today).first()
        if rec:
            rec.checkin_at = datetime.combine(today, time(10, 10))
            rec.checkout_at = None
            rec.exception_granted = False
        else:
            rec = Attendance(user_id=user.id, attendance_date=today, checkin_at=datetime.combine(today, time(10, 10)),
                             checkin_latitude=12.9716, checkin_longitude=77.5946)
            db.session.add(rec)
        db.session.commit()
        record_id = rec.id

        assert rec.is_grace_period is True
        assert rec.status == "Present"

    client = app.test_client()
    login(client, "Employee One")
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"15-minute arrival exception applied" in resp.data

    # Test arrival after 15 mins (10:25 AM) is Late unless exception granted
    with app.app_context():
        rec = db.session.get(Attendance, record_id)
        rec.checkin_at = datetime.combine(today, time(10, 25))
        rec.exception_granted = False
        db.session.commit()
        assert rec.status == "Late"
        assert rec.is_late is True

    # Admin grants exception
    admin_client = app.test_client()
    login(admin_client, "admin@test.local")
    grant_resp = admin_client.post(f"/attendance/{record_id}/grant-exception", follow_redirects=True)
    assert grant_resp.status_code == 200
    with app.app_context():
        updated_rec = db.session.get(Attendance, record_id)
        assert updated_rec.exception_granted is True
        assert updated_rec.status == "Present"


def test_admin_candidate_wise_manual_attendance_and_break_resolution():
    today = now_ist().date()
    admin_client = app.test_client()
    login(admin_client, "admin@test.local")

    with app.app_context():
        emp = User.query.filter_by(full_name="Employee Two").first()
        emp_id = emp.id

    # Admin marks candidate attendance manually because employee phone was switched off / broken
    resp = admin_client.post(
        "/attendance/manual-mark",
        data={
            "user_id": str(emp_id),
            "attendance_date": today.isoformat(),
            "checkin_time": "10:05",
            "checkout_time": "19:00",
            "include_break": "1",
            "break_start_time": "13:00",
            "break_end_time": "14:00",
            "grant_exception": "1",
            "issue_reason": "Phone switched off / dead battery",
            "admin_note": "",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Attendance recorded for Employee Two" in resp.data

    with app.app_context():
        record = Attendance.query.filter_by(user_id=emp_id, attendance_date=today).first()
        assert record is not None
        assert record.marked_by_admin is True
        assert record.admin_note == "Phone switched off / dead battery"
        assert record.break_start_at is not None
        assert record.break_end_at is not None
        # 1-hour break buffer recorded
        assert int((record.break_end_at - record.break_start_at).total_seconds()) == 3600
        assert "01:00 PM – 02:00 PM (60m)" in record.break_display
        assert record.exception_granted is True
        assert record.status == "Present"

    # Quick check-out test: candidate checked in in the morning, phone died during work
    with app.app_context():
        emp1 = User.query.filter_by(full_name="Employee One").first()
        test_rec = Attendance(
            user_id=emp1.id,
            attendance_date=today,
            checkin_at=datetime.combine(today, time(9, 55)),
            checkin_latitude=12.9700,
            checkin_longitude=77.5900,
        )
        db.session.add(test_rec)
        db.session.commit()
        test_rec_id = test_rec.id

    checkout_resp = admin_client.post(f"/attendance/{test_rec_id}/quick-checkout", follow_redirects=True)
    assert checkout_resp.status_code == 200
    with app.app_context():
        checked_out_rec = db.session.get(Attendance, test_rec_id)
        assert checked_out_rec.checkout_at is not None
        assert checked_out_rec.marked_by_admin is True


def test_resolve_employee_issue_from_profile_and_clean_records_page():
    admin_client = app.test_client()
    login(admin_client, "admin@test.local")
    today = now_ist().date()

    with app.app_context():
        emp = User.query.filter_by(full_name="Employee One").first()
        emp_id = emp.id

    # 1. Employees list has clickable row for admin
    emp_list_resp = admin_client.get("/employees")
    assert emp_list_resp.status_code == 200
    assert b"emp-row-clickable" in emp_list_resp.data
    assert f'data-href="/employees/{emp_id}/edit"'.encode() in emp_list_resp.data

    # 2. Employee profile page has grievance section
    edit_page_resp = admin_client.get(f"/employees/{emp_id}/edit")
    assert edit_page_resp.status_code == 200
    assert b"Resolve Attendance Issue" in edit_page_resp.data
    assert f'action="/employees/{emp_id}/resolve-issue"'.encode() in edit_page_resp.data

    # 3. Admin submits grievance resolution from the employee's profile
    resolve_resp = admin_client.post(
        f"/employees/{emp_id}/resolve-issue",
        data={
            "attendance_date": today.isoformat(),
            "checkin_time": "10:10",
            "checkout_time": "19:00",
            "include_break": "1",
            "grant_exception": "1",
            "issue_reason": "Phone broken / damaged device",
            "admin_note": "",
        },
        follow_redirects=True,
    )
    assert resolve_resp.status_code == 200
    assert b"Attendance grievance resolved" in resolve_resp.data

    # Verify database state
    with app.app_context():
        record = Attendance.query.filter_by(user_id=emp_id, attendance_date=today).first()
        assert record is not None
        assert record.marked_by_admin is True
        assert record.admin_note == "Phone broken / damaged device"
        assert record.exception_granted is True
        assert record.status == "Present"

    # 4. Records page does not contain manual attendance modal or "Resolve Candidate Attendance" button
    records_resp = admin_client.get("/records")
    assert records_resp.status_code == 200
    assert b"Resolve Candidate Attendance" not in records_resp.data
    assert b'id="manualAttendanceModal"' not in records_resp.data
    assert b"Admin Resolved" in records_resp.data


def test_admin_overview_no_charts_and_no_my_attendance():
    admin_client = app.test_client()
    login(admin_client, "admin@test.local")

    # 1. Admin overview page should NOT have charts (Attendance trend, Today's distribution, canvas)
    dash_resp = admin_client.get("/dashboard")
    assert dash_resp.status_code == 200
    assert b"Attendance trend" not in dash_resp.data
    assert b"Today's distribution" not in dash_resp.data
    assert b"attendanceTrend" not in dash_resp.data
    assert b"attendanceDistribution" not in dash_resp.data

    # 2. KPI metrics and Recent attendance table ARE present
    assert b"Active employees" in dash_resp.data
    assert b"Recent attendance" in dash_resp.data

    # 3. Sidebar for admin should NOT contain "My attendance"
    assert b"My attendance" not in dash_resp.data

    # 4. Accessing /attendance as admin redirects to /dashboard
    att_resp = admin_client.get("/attendance", follow_redirects=False)
    assert att_resp.status_code == 302
    assert att_resp.location.endswith("/dashboard")


def test_health_check_endpoints():
    client = app.test_client()
    for endpoint in ["/health", "/healthz"]:
        resp = client.get(endpoint)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "timestamp" in data


def test_security_headers_enforced():
    client = app.test_client()
    resp = client.get("/login")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "geolocation=(self)" in resp.headers.get("Permissions-Policy", "")


def test_sqlite_foreign_key_constraints_enforced():
    import pytest
    from sqlalchemy.exc import IntegrityError
    with app.app_context():
        # Attempt to insert attendance for non-existent user ID 99999
        orphan = Attendance(
            user_id=99999,
            attendance_date=now_ist().date(),
            checkin_at=now_ist(),
            checkin_latitude=12.97,
            checkin_longitude=77.59,
        )
        db.session.add(orphan)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_geofence_accuracy_policy():
    client = app.test_client()
    login(client, "Employee One")

    # 1. Imprecise accuracy (> 500m) is rejected
    bad_acc = client.post("/api/attendance/check-in", json={
        "latitude": 12.9700,
        "longitude": 77.5900,
        "accuracy": 850.0
    })
    assert bad_acc.status_code == 400
    assert b"accuracy is too imprecise" in bad_acc.data.lower()

    # 2. Negative or non-numeric accuracy is rejected
    invalid_acc = client.post("/api/attendance/check-in", json={
        "latitude": 12.9700,
        "longitude": 77.5900,
        "accuracy": -25.0
    })
    assert invalid_acc.status_code == 400

    # 3. Valid accuracy (< 500m) within geofence is accepted
    good_acc = client.post("/api/attendance/check-in", json={
        "latitude": 12.9700,
        "longitude": 77.5900,
        "accuracy": 15.0
    })
    assert good_acc.status_code == 201


def test_checkout_while_on_break_concludes_break_safely():
    client = app.test_client()
    login(client, "Employee One")

    # Check in
    client.post("/api/attendance/check-in", json={"latitude": 12.9700, "longitude": 77.5900})
    # Start break
    client.post("/api/attendance/break-start")
    with app.app_context():
        rec = Attendance.query.filter_by(user_id=get_user("employee@test.local").id, attendance_date=now_ist().date()).first()
        assert rec.break_in_progress is True

    # Checkout without explicit break-end should auto-close break cleanly
    cout = client.post("/api/attendance/check-out", json={"latitude": 12.9700, "longitude": 77.5900})
    assert cout.status_code == 200

    with app.app_context():
        rec = Attendance.query.filter_by(user_id=get_user("employee@test.local").id, attendance_date=now_ist().date()).first()
        assert rec.checkout_at is not None
        assert rec.break_start_at is not None
        assert rec.break_end_at is not None
        assert rec.break_in_progress is False


def test_login_rate_limiter_logic():
    from app import LoginRateLimiter
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=60)
    key = "127.0.0.1:test_user"

    is_locked, _ = limiter.is_locked(key)
    assert not is_locked

    # 1st failure
    locked, _ = limiter.record_failure(key)
    assert not locked

    # 2nd failure
    locked, _ = limiter.record_failure(key)
    assert not locked

    # 3rd failure locks the account
    locked, rem = limiter.record_failure(key)
    assert locked
    assert rem > 0

    is_locked, rem2 = limiter.is_locked(key)
    assert is_locked
    assert rem2 > 0

    # Successful login resets the lockout
    limiter.record_success(key)
    is_locked, _ = limiter.is_locked(key)
    assert not is_locked


def test_records_page_has_compact_action_dropdown_and_no_standalone_admin_help_button():
    admin_client = app.test_client()
    login(admin_client, "admin@test.local")
    today = now_ist().date()
    with app.app_context():
        employee = get_user("employee@test.local")
        rec = Attendance.query.filter_by(user_id=employee.id, attendance_date=today).first()
        if not rec:
            db.session.add(Attendance(
                user_id=employee.id,
                attendance_date=today,
                checkin_at=datetime.combine(today, time(10, 5)),
                checkout_at=None,
                checkin_latitude=12.97,
                checkin_longitude=77.59,
            ))
            db.session.commit()

    resp = admin_client.get("/records")
    assert resp.status_code == 200

    # Compact Manage Attendance dropdown is rendered
    assert b"Manage Attendance" in resp.data
    assert b"action-dropdown" in resp.data
    assert b"action-menu" in resp.data

    # Old standalone Admin Help button is no longer present as a separate button in Actions column
    assert b'title="Help employee: Excuse lateness and mark Present"' not in resp.data


def test_employee_edit_page_no_longer_has_access_roles_sidebar_and_form_expands():
    admin_client = app.test_client()
    login(admin_client, "admin@test.local")
    with app.app_context():
        emp = get_user("employee@test.local")
        emp_id = emp.id

    resp = admin_client.get(f"/employees/{emp_id}/edit")
    assert resp.status_code == 200

    # Verify Access Roles sidebar panel was removed
    assert b"permission-guide" not in resp.data
    assert b"Access Roles" not in resp.data
    assert b"form-page-single" in resp.data

    # Verify Access Role form field in main form remains fully functional
    assert b'id="role"' in resp.data
    assert b'name="role"' in resp.data

    # Verify updating the employee retains role assignment functionality
    post_resp = admin_client.post(
        f"/employees/{emp_id}/edit",
        data={
            "full_name": emp.full_name,
            "department": emp.department,
            "shift_timing": emp.shift_timing,
            "job_title": emp.job_title,
            "phone": emp.phone,
            "email": "",
            "role": "manager",
            "password": "",
        },
        follow_redirects=True,
    )
    # Manager requires email
    assert post_resp.status_code == 200
    assert b"A work email is required for Admin and Manager accounts" in post_resp.data

    # With email provided, role update succeeds
    post_ok = admin_client.post(
        f"/employees/{emp_id}/edit",
        data={
            "full_name": emp.full_name,
            "department": emp.department,
            "shift_timing": emp.shift_timing,
            "job_title": emp.job_title,
            "phone": emp.phone,
            "email": "emp.promoted@balajitransports.com",
            "role": "manager",
            "password": "",
        },
        follow_redirects=True,
    )
    assert post_ok.status_code == 200
    with app.app_context():
        updated_emp = db.session.get(User, emp_id)
        assert updated_emp.role == "manager"
        # Reset back to employee for test isolation
        updated_emp.role = "employee"
        updated_emp.email = f"{updated_emp.phone}@no-email.invalid"
        db.session.commit()


def test_dashboard_has_no_non_working_day_banner_or_attendance_rate_card():
    admin_client = app.test_client()
    login(admin_client, "admin@test.local")
    resp = admin_client.get("/dashboard")
    assert resp.status_code == 200

    # Requirement 1: Non-working day banner removed
    assert b"Non-working day" not in resp.data
    assert b"Monday\xe2\x80\x93Friday working-week assumption" not in resp.data
    assert b"Not counted on weekends" not in resp.data

    # Requirement 2: Attendance rate card removed
    assert b"Attendance rate" not in resp.data
    assert b"kpi-rate" not in resp.data

    # Requirement 6: Interactive cards present
    assert b'data-modal-type="active-employees"' in resp.data
    assert b'data-modal-type="present-employees"' in resp.data
    assert b'data-modal-type="late-employees"' in resp.data
    assert b'id="dashboardModal"' in resp.data


def test_api_dashboard_active_employees_requires_roles_and_returns_active_only():
    # 1. Unauthenticated redirects to login
    client = app.test_client()
    anon_resp = client.get("/api/dashboard/active-employees")
    assert anon_resp.status_code == 302

    # 2. Ordinary employee receives 403 Forbidden
    login(client, "Employee One")
    emp_resp = client.get("/api/dashboard/active-employees")
    assert emp_resp.status_code == 403

    # 3. Admin receives active employees list without deactivated ones
    admin_client = app.test_client()
    login(admin_client, "admin@test.local")
    
    # Deactivate one user to ensure it is excluded
    with app.app_context():
        deact = get_user("other@test.local")
        deact.active = False
        db.session.commit()

    resp = admin_client.get("/api/dashboard/active-employees")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["count"] == len(data["employees"])
    emp_names = [e["full_name"] for e in data["employees"]]
    assert "Employee Two" not in emp_names
    assert "Employee One" in emp_names

    # Clean up deactivated user
    with app.app_context():
        deact = get_user("other@test.local")
        deact.active = True
        db.session.commit()


def test_api_dashboard_present_and_late_employees_date_filtered():
    admin_client = app.test_client()
    login(admin_client, "admin@test.local")
    today = now_ist().date()

    with app.app_context():
        emp = get_user("employee@test.local")
        # Ensure employee has a late check-in (shift is 10:00 AM, checkin at 10:35 AM is late)
        existing = Attendance.query.filter_by(user_id=emp.id, attendance_date=today).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()

        rec = Attendance(
            user_id=emp.id,
            attendance_date=today,
            checkin_at=datetime.combine(today, time(10, 35)),
            checkout_at=datetime.combine(today, time(19, 5)),
            checkin_latitude=12.97,
            checkin_longitude=77.59,
        )
        db.session.add(rec)
        db.session.commit()

    # Present employees API
    resp_present = admin_client.get(f"/api/dashboard/present-employees?date={today.isoformat()}")
    assert resp_present.status_code == 200
    pdata = resp_present.get_json()
    assert pdata["ok"] is True
    assert pdata["count"] >= 1
    p_names = [r["full_name"] for r in pdata["records"]]
    assert "Employee One" in p_names
    emp_rec = next(r for r in pdata["records"] if r["full_name"] == "Employee One")
    assert emp_rec["shift_completed"] is True
    assert emp_rec["status"] == "Late"

    # Late employees API
    resp_late = admin_client.get(f"/api/dashboard/late-employees?date={today.isoformat()}")
    assert resp_late.status_code == 200
    ldata = resp_late.get_json()
    assert ldata["ok"] is True
    assert ldata["count"] >= 1
    late_rec = next(r for r in ldata["records"] if r["full_name"] == "Employee One")
    assert "mins late" in late_rec["lateness_display"]
    assert late_rec["shift_start"] == "10:00 AM"

    # Absent employees API
    resp_absent = admin_client.get(f"/api/dashboard/absent-employees?date={today.isoformat()}")
    assert resp_absent.status_code == 200
    adata = resp_absent.get_json()
    assert adata["ok"] is True
    # Employee One has check-in today, so must NOT be in absent list
    absent_names = [e["full_name"] for e in adata["employees"]]
    assert "Employee One" not in absent_names


def test_logout_invalidates_session_and_clears_cookies():
    client = app.test_client()
    login(client, "Employee One")
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert "no-store" in dash.headers.get("Cache-Control", "")

    # Logout via POST
    logout_resp = client.post("/logout", follow_redirects=False)
    assert logout_resp.status_code == 302
    assert logout_resp.location == "/login" or logout_resp.location.endswith("/login")
    assert "no-store" in logout_resp.headers.get("Cache-Control", "")
    assert "max-age=0" in logout_resp.headers.get("Cache-Control", "")

    # Protected page now redirects to login
    dash_after = client.get("/dashboard", follow_redirects=False)
    assert dash_after.status_code == 302
    assert "/login" in dash_after.location


def test_logout_requires_post_and_clears_session():
    client = app.test_client()
    login(client, "Employee One")
    # GET /logout is rejected (POST-only for CSRF safety)
    get_resp = client.get("/logout", follow_redirects=False)
    assert get_resp.status_code == 405

    logout_resp = client.post("/logout", follow_redirects=False)
    assert logout_resp.status_code == 302
    assert "/login" in logout_resp.location

    # Re-accessing dashboard redirects to login
    dash_after = client.get("/dashboard", follow_redirects=False)
    assert dash_after.status_code == 302
    assert "/login" in dash_after.location


def test_sequential_employee_logins_are_strictly_isolated():
    client = app.test_client()

    # 1. Employee One logs in
    login(client, "Employee One")
    dash1 = client.get("/dashboard")
    assert dash1.status_code == 200
    assert b"Employee One" in dash1.data
    assert b"Employee Two" not in dash1.data

    # 2. Logout
    client.post("/logout", follow_redirects=True)

    # 3. Employee Two logs in
    login(client, "Employee Two")
    dash2 = client.get("/dashboard")
    assert dash2.status_code == 200
    assert b"Employee Two" in dash2.data
    assert b"Employee One" not in dash2.data


def test_manager_department_isolation_on_attendance_modifications():
    """Verify managers cannot mark attendance, grant exceptions, or checkout employees from other branches."""
    today = now_ist().date()
    manager_client = app.test_client()
    login(manager_client, "manager@test.local")  # Tumkur (Satyamangala) branch

    with app.app_context():
        emp2 = User.query.filter_by(email="other@test.local").first()
        emp2.branch = "Bangalore (Whitefield)"
        emp2_id = emp2.id

        # Create an attendance record for Employee Two in Whitefield
        rec = Attendance(
            user_id=emp2_id,
            attendance_date=today,
            checkin_at=datetime.combine(today, time(10, 30)),
            checkin_latitude=12.9700,
            checkin_longitude=77.5900,
            branch="Bangalore (Whitefield)",
        )
        db.session.add(rec)
        db.session.commit()
        rec_id = rec.id

    # 1. Manager attempts manual-mark for employee in other department -> 403
    resp_manual = manager_client.post(
        "/attendance/manual-mark",
        data={
            "user_id": str(emp2_id),
            "attendance_date": today.isoformat(),
            "checkin_time": "10:00",
            "checkout_time": "19:00",
        },
    )
    assert resp_manual.status_code == 403

    # 2. Manager attempts grant-exception for employee in other department -> 403
    resp_grant = manager_client.post(f"/attendance/{rec_id}/grant-exception")
    assert resp_grant.status_code == 403

    # 3. Manager attempts quick-checkout for employee in other department -> 403
    resp_cout = manager_client.post(f"/attendance/{rec_id}/quick-checkout")
    assert resp_cout.status_code == 403


def test_manager_can_modify_own_department_attendance():
    """Verify managers can resolve attendance for employees within their own department."""
    today = now_ist().date()
    manager_client = app.test_client()
    login(manager_client, "manager@test.local")  # Operations department

    with app.app_context():
        emp1 = User.query.filter_by(email="employee@test.local").first()  # Operations department
        assert emp1.department == "Operations"
        emp1_id = emp1.id

    # Manager marks manual attendance for Employee One
    resp = manager_client.post(
        "/attendance/manual-mark",
        data={
            "user_id": str(emp1_id),
            "attendance_date": today.isoformat(),
            "checkin_time": "10:00",
            "checkout_time": "19:00",
            "admin_note": "Approved by Operations Manager",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        rec = Attendance.query.filter_by(user_id=emp1_id, attendance_date=today).first()
        assert rec is not None
        assert rec.marked_by_admin is True
        assert "Approved by Operations Manager" in rec.admin_note


def test_manager_sees_all_departments_within_own_branch():
    """Verify a branch-scoped manager sees employees from other departments in the same branch."""
    with app.app_context():
        emp2 = get_user("other@test.local")  # Fleet department, Tumkur (Satyamangala) branch
        assert emp2.department == "Fleet"
        assert emp2.branch == "Tumkur (Satyamangala)"
    client = app.test_client()
    login(client, "manager@test.local")
    response = client.get("/employees")
    assert b"Employee One" in response.data
    assert b"Employee Two" in response.data


def test_admin_sqlite_backup_download_and_rbac():
    """Verify only admins can download a valid SQLite backup snapshot."""
    admin_client = app.test_client()
    login(admin_client, "admin@test.local")
    resp = admin_client.get("/admin/backup.sqlite3")
    assert resp.status_code == 200
    assert resp.data.startswith(b"SQLite format 3\x00")
    assert "balaji-workforce-backup-" in resp.headers.get("Content-Disposition", "")

    manager_client = app.test_client()
    login(manager_client, "manager@test.local")
    assert manager_client.get("/admin/backup.sqlite3").status_code == 403

    emp_client = app.test_client()
    login(emp_client, "Employee One")
    assert emp_client.get("/admin/backup.sqlite3").status_code == 403


def test_records_and_reports_branch_filtering():
    """Verify admins can filter /records and /reports by branch."""
    today = now_ist().date()
    with app.app_context():
        emp1 = get_user("employee@test.local")
        emp2 = get_user("other@test.local")
        emp2.branch = "Bangalore (Whitefield)"
        db.session.add_all([
            Attendance(user_id=emp1.id, attendance_date=today, checkin_at=datetime.combine(today, time(10, 0)),
                       checkin_latitude=12.97, checkin_longitude=77.59, branch="Tumkur (Satyamangala)"),
            Attendance(user_id=emp2.id, attendance_date=today, checkin_at=datetime.combine(today, time(10, 0)),
                       checkin_latitude=12.97, checkin_longitude=77.59, branch="Bangalore (Whitefield)"),
        ])
        db.session.commit()

    admin_client = app.test_client()
    login(admin_client, "admin@test.local")

    rec_wf = admin_client.get("/records?branch=Bangalore+(Whitefield)")
    assert rec_wf.status_code == 200
    rec_tbody = rec_wf.data.split(b"<tbody>")[1].split(b"</tbody>")[0]
    assert b"Employee Two" in rec_tbody
    assert b"Employee One" not in rec_tbody

    rep_wf = admin_client.get(f"/reports?start={today.isoformat()}&end={today.isoformat()}&branch=Bangalore+(Whitefield)")
    assert rep_wf.status_code == 200
    rep_tbody = rep_wf.data.split(b"<tbody>")[1].split(b"</tbody>")[0]
    assert b"Employee Two" in rep_tbody
    assert b"Employee One" not in rep_tbody


def test_whitefield_branch_geofence_isolation():
    """Verify Whitefield staff fail closed without Whitefield coords and validate against Whitefield once set."""
    with app.app_context():
        emp2 = get_user("other@test.local")
        emp2.branch = "Bangalore (Whitefield)"
        db.session.commit()

    wf_client = app.test_client()
    login(wf_client, "other@test.local")

    # 1. Whitefield coords blank -> 503 even though Tumkur coords are configured
    unconfigured = wf_client.post("/api/attendance/check-in", json={"latitude": 12.9700, "longitude": 77.5900})
    assert unconfigured.status_code == 503
    assert b"bangalore (whitefield)" in unconfigured.data.lower()

    # 2. Configure Whitefield coords -> Tumkur coords rejected (403), Whitefield coords accepted (201)
    app.config.update(
        WHITEFIELD_GEOFENCE_LATITUDE="12.9698",
        WHITEFIELD_GEOFENCE_LONGITUDE="77.7499",
        WHITEFIELD_GEOFENCE_RADIUS_METERS="200",
    )
    try:
        wrong_branch = wf_client.post("/api/attendance/check-in", json={"latitude": 13.3698889, "longitude": 77.1190278})
        assert wrong_branch.status_code == 403
        assert b"bangalore (whitefield)" in wrong_branch.data.lower()

        ok_checkin = wf_client.post("/api/attendance/check-in", json={"latitude": 12.9698, "longitude": 77.7499})
        assert ok_checkin.status_code == 201
        assert ok_checkin.get_json()["branch"] == "Bangalore (Whitefield)"
    finally:
        app.config.pop("WHITEFIELD_GEOFENCE_LATITUDE", None)
        app.config.pop("WHITEFIELD_GEOFENCE_LONGITUDE", None)
        app.config.pop("WHITEFIELD_GEOFENCE_RADIUS_METERS", None)


def test_pwa_manifest_service_worker_and_install_prompt():
    """Verify PWA manifest, service worker, icons, and install banner markup."""
    client = app.test_client()

    manifest = client.get("/manifest.json")
    assert manifest.status_code == 200
    assert manifest.mimetype == "application/manifest+json"
    m_json = manifest.get_json()
    assert m_json["display"] == "standalone"
    assert len(m_json["icons"]) >= 2

    sw = client.get("/sw.js")
    assert sw.status_code == 200
    assert sw.headers.get("Service-Worker-Allowed") == "/"
    assert "no-cache" in sw.headers.get("Cache-Control", "")

    icon192 = client.get("/static/icons/icon-192.png")
    icon512 = client.get("/static/icons/icon-512.png")
    assert icon192.status_code == 200 and icon192.data.startswith(b"\x89PNG")
    assert icon512.status_code == 200 and icon512.data.startswith(b"\x89PNG")

    login_page = client.get("/login")
    assert login_page.status_code == 200
    assert b"manifest.json" in login_page.data
    assert b"serviceWorker" in login_page.data
    assert b"pwaInstallBanner" in login_page.data


def test_download_apk_requires_authentication():
    """Verify /download-apk and /apk require a logged-in user."""
    client = app.test_client()
    for path in ("/download-apk", "/apk"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.location


def test_seed_initial_accounts_respects_env_vars_in_production(monkeypatch):
    """Verify seed_initial_accounts never seeds a hardcoded weak password when env var is missing."""
    from app import seed_initial_accounts

    with app.app_context():
        # Clear existing admin accounts to test fresh seeding behavior
        User.query.filter_by(role="admin").delete()
        db.session.commit()

        monkeypatch.setenv("FLASK_ENV", "production")
        monkeypatch.delenv("INITIAL_ADMIN_PASSWORD", raising=False)
        seed_initial_accounts()
        assert User.query.filter_by(role="admin").first() is None

        monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "owner@balaji.test")
        monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "Str0ngEnvPass!99")
        seed_initial_accounts()
        seeded = User.query.filter_by(email="owner@balaji.test").first()
        assert seeded is not None
        assert seeded.role == "admin"
        assert seeded.check_password("Str0ngEnvPass!99")


def test_quick_checkout_closes_active_break_and_accumulates_seconds():
    """Verify admin quick_checkout closes an in-progress break before setting checkout_at."""
    from datetime import timedelta
    today = now_ist().date()
    with app.app_context():
        emp = get_user("employee@test.local")
        rec = Attendance(
            user_id=emp.id,
            attendance_date=today,
            checkin_at=datetime.combine(today, time(10, 0)),
            checkin_latitude=12.97,
            checkin_longitude=77.59,
            break_start_at=now_ist() - timedelta(minutes=12),
            break_end_at=None,
            total_break_seconds=180,
            branch=emp.branch,
        )
        db.session.add(rec)
        db.session.commit()
        rec_id = rec.id

    admin_client = app.test_client()
    login(admin_client, "admin@test.local")
    resp = admin_client.post(f"/attendance/{rec_id}/quick-checkout", follow_redirects=False)
    assert resp.status_code == 302

    with app.app_context():
        updated = db.session.get(Attendance, rec_id)
        assert updated.checkout_at is not None
        assert updated.break_end_at is not None
        assert not updated.break_in_progress
        assert updated.total_break_seconds >= 180 + 11 * 60


def test_admin_attendance_rejects_invalid_checkout_and_break_order():
    """Verify manual_mark_attendance validates checkout > checkin and break_end > break_start."""
    today = now_ist().date()
    with app.app_context():
        emp = get_user("employee@test.local")
        emp_id = emp.id

    admin_client = app.test_client()
    login(admin_client, "admin@test.local")

    bad_checkout = admin_client.post(
        "/attendance/manual-mark",
        data={
            "user_id": str(emp_id),
            "attendance_date": today.isoformat(),
            "checkin_time": "10:00",
            "checkout_time": "09:30",
        },
        follow_redirects=True,
    )
    assert bad_checkout.status_code == 200
    assert b"check-out time must be after check-in time" in bad_checkout.data.lower()

    bad_break = admin_client.post(
        "/attendance/manual-mark",
        data={
            "user_id": str(emp_id),
            "attendance_date": today.isoformat(),
            "checkin_time": "10:00",
            "checkout_time": "19:00",
            "include_break": "on",
            "break_start_time": "14:00",
            "break_end_time": "13:00",
        },
        follow_redirects=True,
    )
    assert bad_break.status_code == 200
    assert b"break end time must be after break start time" in bad_break.data.lower()


def test_employee_cannot_access_administrative_endpoints():
    """Verify employees cannot access admin/manager-only routes."""
    employee_client = app.test_client()
    login(employee_client, "Employee One")

    # Employee cannot access /employees
    assert employee_client.get("/employees").status_code == 403

    # Employee cannot access /reports
    assert employee_client.get("/reports").status_code == 403
    assert employee_client.get("/reports.csv").status_code == 403
    assert employee_client.get("/reports.xlsx").status_code == 403
    assert employee_client.get("/reports/daily").status_code == 403

    # Employee cannot access employee creation or editing
    assert employee_client.get("/employees/new").status_code == 403
    assert employee_client.get("/employees/1/edit").status_code == 403

    # Employee cannot manually mark attendance
    assert employee_client.post("/attendance/manual-mark", data={}).status_code == 403


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main(["-v", __file__]))






