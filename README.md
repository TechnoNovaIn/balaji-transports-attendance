# Balaji Transports — Attendance Management System

A local interview-demo prototype for a transport workforce. It demonstrates Flask, SQLite, role-based access control (RBAC), browser GPS capture, attendance analytics, CSV reporting, and a color-coded Excel export. Use fictional data only.

## Features

- Session-based authentication using Flask-Login and Werkzeug password hashing.
- Three roles: **Admin**, **Manager**, and **Employee**. Role checks run on the server. Managers are scoped to their department; employees can view and record only their own attendance.
- GPS-based check-in and check-out using the browser Geolocation API. The backend validates coordinate ranges, timestamps attendance on the server, and enforces a factory geofence before accepting either action.
- Admin-only employee status management: filter active, disabled, or all accounts; disable an account to block sign-in; re-enable it later.
- One attendance record per employee per local India date; duplicate check-in and invalid checkout attempts are rejected.
- Responsive dashboard with database-backed KPIs and Chart.js charts, employee search, attendance filters, reports, and a color-coded Excel export.
- CSV and XLSX reports. The XLSX report highlights Normal/On Time in green and Late/Early in red; CSV cannot preserve colors.
- SQLite database, idempotent demo seed script, and automated tests.

## Requirements

- Python 3.10+ (Python 3.11 or 3.12 recommended)
- A modern browser. Internet access is required for the Google Fonts, Bootstrap Icons, and Chart.js CDN assets. The core forms work locally without those presentation assets.

## Windows setup (PowerShell)

Open a terminal in this project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts/init_db.py
python scripts/seed_demo.py
python app.py
```

If PowerShell blocks environment activation, use Command Prompt:

```cmd
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts\init_db.py
python scripts\seed_demo.py
python app.py
```

You can also double-click `setup_and_run.bat`; it creates the virtual environment, installs requirements, initializes the database, seeds demo data, and starts the development server. This requires internet access for the Python packages on first run.

Open **http://127.0.0.1:5000**. GPS is supported on localhost in modern browsers. Allow location access when the app requests it. The app does not silently create coordinates if location access fails.

## Demo accounts

All demo accounts use the password `DemoPass123!` for the local demonstration:

| Role | Sign-in identifier | Scope |
| --- | --- | --- |
| Admin | `admin@balaji.demo` (email) | All departments, users, attendance, reports |
| Manager | `manager@balaji.demo` (email) | Tally department only |
| Employee | `Kiran Kumar` or `BW-1003` (name/login ID) | Personal attendance only |
| Employee | `Meera Nair` or `BW-1004` (name/login ID) | Personal attendance only |
| Employee | `Arjun Patil` or `BW-1005` (name/login ID) | Personal attendance only |

The seed script adds demo users when missing and preserves existing passwords and active/disabled status. Historical demo checkout times may be refreshed so most demo records are On Time and a smaller portion are Early. It does not create fictional attendance for today. The examples are fictional and must not be treated as actual attendance evidence.

## Roles and behavior

- **Admin:** manage users and roles; view all attendance data; export CSV reports.
- **Manager:** read-only employee and attendance views limited to their department; view reports and export CSV.
- **Employee:** record personal check-in/out and view personal attendance history.
- Shift start is **10:00 AM** with a grace period through **10:15 AM inclusive**; check-ins after 10:15 AM are Late. Early check-ins keep the actual timestamp in the database but the report displays an attendance-credit time of 10:00 AM. Checkouts before **7:00 PM** are Early; at or after 7:00 PM are On Time. These are prototype rules and should be confirmed with management.
- Absence and attendance rate on the dashboard are simplified metrics. Weekdays Monday–Friday are assumed to be expected working days; real deployments need roster, leave, holiday, shift and off-day rules.
- The prototype permits one attendance entry per employee per calendar date. Overnight shifts, breaks, overtime, leave, and multiple shifts are not modelled.

## Database and configuration

The default database is `instance/balaji_workforce.sqlite3`. `db.create_all()` creates missing tables and does not wipe existing rows. To choose a different database, set the `DATABASE_URL` environment variable. Set a unique random `SECRET_KEY` outside source control before running in any shared environment.

### Factory geofence configuration

The factory geofence is hardcoded in `app.py` for this demonstration: latitude `13.3698889`, longitude `77.1190278`, radius `200` metres. Verify the coordinates and allowed radius against the company's approved location and policy before use. The server uses the Haversine formula to compare browser-reported coordinates with the factory centre. Both check-in and check-out are rejected if outside the radius. Browser geolocation can be spoofed and is not proof of identity or physical presence by itself.

## Tests

```powershell
pytest -q
```

Tests use an isolated temporary SQLite database and cover login/password hashing, access control, attendance validation, geofence rejection for check-in and check-out, missing geofence configuration, employee enable/disable flows, cross-employee access, CSV generation, optional employee ID/email entry, and the daily owner report.

## Security and production limitations

This is a demonstration, not a production-ready HR system. Before deployment, configure HTTPS, a strong secret key, secure cookie settings, CSRF protection appropriate to the deployment, login rate limiting, password-reset and account-recovery flows, audit logs, backups, retention rules, stricter admin provisioning, and a production WSGI server. The current app has basic session CSRF tokens for form and GPS POST requests. Browser location can be spoofed and is not cryptographic proof of physical presence; geofencing and independent device controls would be needed for stronger validation. Confirm employee notice and consent, access/retention policy, shift rules and holidays with the company. Do not expose this development server directly to the internet.

## Architecture

`Browser (HTML/CSS/JS)` → `Flask routes + Flask-Login + server-side RBAC` → `SQLAlchemy models` → `SQLite` → `dashboard aggregates / CSV export`.

GPS coordinates are read by the browser only after a user presses Check In or Check Out and grants permission, then submitted to the Flask backend. The server decides the timestamp and associates the record with the authenticated user rather than accepting an employee ID from the browser.


### Windows timezone dependency

The project includes `tzdata` because Windows Python installations may not have an IANA timezone database available by default. If the timezone `Asia/Kolkata` cannot be found, install dependencies again with `python -m pip install -r requirements.txt`.


## Recent consolidated update

This package includes a matching Flask backend and report template. The Reports page registers both `/reports.csv` and `/reports.xlsx`; use the Excel button for green/red formatting. The export columns are Date, Employee Name, Department, Role, Login Status, Login Time, Logout Time, and Logout Status. Normal/On Time statuses are green, while Late/Early statuses are red. CSV files contain the same values but cannot preserve cell colours.

The configured attendance policy is a 10:00 AM shift start, grace through 10:15 AM inclusive, and a 7:00 PM shift end. Arrivals before 10:00 AM display as 10:00 AM in the report while the original timestamp is preserved in the database. This prototype's reports classify checkouts before 7:00 PM as Early and at/after 7:00 PM as On Time. Confirm policy details with company management before production use.

The employee dashboard query is scoped to the current employee, and employee creation uses these department choices: Tally, AI, Accounts, Billing, Finance, Writer, Tyre Department, Inventory.

Factory geofence defaults to latitude 13.3698889, longitude 77.1190278, radius 200 metres. Verify the coordinates and radius at the actual site before relying on them.

For local use on Windows, run `setup_and_run.bat`, or use the `.venv` Python interpreter to install requirements, initialise the database, seed demo data, and start Flask. Keep `.git`, `.venv`, and any local database files when extracting an update over an existing checkout. Do not run the demo seeder against real employee attendance data.


## Optional employee ID and email

Company Employee ID and work email are optional when creating or editing employees. The required fields for a new employee account are full name, department, job title, access role, and a password of at least eight characters. Department and access role must be selected explicitly; the form does not silently choose a default for new accounts. If the ID is omitted, the application assigns a `SYS-...` reference for database compatibility; this assigned login ID can be used on the Employee Login page. If an employee email is omitted, the application stores a non-deliverable internal placeholder for compatibility with the current database schema and displays “No email provided.” The application has separate login pages: Admin/Manager use `/login` with registered work email and password; employees use `/employee-login` with their full name OR assigned login ID and password. Employee email is not used for employee login. Active employee full names should be unique; if names collide, the generated or assigned login ID provides an unambiguous alternative. Admin and Manager accounts must have a work email.

## Daily owner report

Administrators can open **Reports → Daily owner report** (or visit `/reports/daily`) to review a selected date. The report lists active non-admin workforce accounts with only employee name, login status, and logout status—no check-in or check-out times—and includes employees with no recorded check-in. An employee who has checked in but has not checked out is marked **Pending**, not **On Time**. Use **Download daily CSV** to save the report. For today's date, employees are not marked absent until the scheduled 7:00 PM shift end; past weekdays with no attendance are listed as absent. This is an on-demand report page, not an automatically emailed scheduled report.


## Sign-in rules

Admins and Managers sign in using their registered work email and password. Employees sign in at `/employee-login` using the exact full name recorded in the employee account OR their assigned login ID and password. Employee email addresses are not accepted for employee login; a generated `SYS-...` login ID is accepted. Active employee full names must be unique so the login is unambiguous. A work email is required for Admin and Manager account creation; it is optional for employee accounts.
