import os
import tempfile
from datetime import datetime, time

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


def test_manager_employee_scope_is_department_limited():
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
    assert b"Date,Employee Name,Department,Role,Login Status,Login Time,Logout Time,Logout Status" in response.data
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
    assert b"Employee Name,Login Status,Logout Status" in csv_response.data
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
