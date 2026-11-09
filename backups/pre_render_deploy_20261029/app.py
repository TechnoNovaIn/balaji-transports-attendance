"""Balaji Transports — attendance management demo application.

This project is an interview prototype. Review README.md before using it beyond local demo.
"""
from __future__ import annotations

import csv
import io
import math
import os
import secrets
import xlsxwriter
from datetime import date, datetime, time, timedelta
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import (Flask, abort, current_app, flash, jsonify, make_response,
                   redirect, render_template, request, url_for)
from flask_login import (LoginManager, UserMixin, current_user, login_required,
                         login_user, logout_user)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, func, or_
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
IST = ZoneInfo("Asia/Kolkata")
DEFAULT_SHIFT_START = time(10, 0)
DEFAULT_LATE_AFTER = time(10, 15)
DEFAULT_SHIFT_END = time(19, 0)

app = Flask(__name__, instance_relative_config=True)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-this-before-deployment"),
    SQLALCHEMY_DATABASE_URI=os.environ.get(
        "DATABASE_URL", f"sqlite:///{(Path(app.instance_path) / 'balaji_workforce.sqlite3').as_posix()}"
    ),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    # Factory geofence configuration (hardcoded in code, per demo setup).
    GEOFENCE_LATITUDE="13.3698889",
    GEOFENCE_LONGITUDE="77.1190278",
    GEOFENCE_RADIUS_METERS="200",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    REMEMBER_COOKIE_HTTPONLY=True,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)
Path(app.instance_path).mkdir(parents=True, exist_ok=True)

db = SQLAlchemy(app)


def ensure_db_schema():
    """Ensure database tables and columns exist for existing SQLite databases."""
    with app.app_context():
        try:
            db.create_all()
            with db.engine.connect() as conn:
                res = conn.execute(db.text("PRAGMA table_info(users)")).fetchall()
                cols = {r[1] for r in res}
                if "phone" not in cols:
                    conn.execute(db.text("ALTER TABLE users ADD COLUMN phone VARCHAR(30)"))
                if "shift_timing" not in cols:
                    conn.execute(db.text("ALTER TABLE users ADD COLUMN shift_timing VARCHAR(40) DEFAULT '10:00 AM - 07:00 PM'"))

                att_res = conn.execute(db.text("PRAGMA table_info(attendance)")).fetchall()
                att_cols = {r[1] for r in att_res}
                if "break_start_at" not in att_cols:
                    conn.execute(db.text("ALTER TABLE attendance ADD COLUMN break_start_at DATETIME"))
                if "break_end_at" not in att_cols:
                    conn.execute(db.text("ALTER TABLE attendance ADD COLUMN break_end_at DATETIME"))
                if "exception_granted" not in att_cols:
                    conn.execute(db.text("ALTER TABLE attendance ADD COLUMN exception_granted BOOLEAN DEFAULT 0"))
                if "marked_by_admin" not in att_cols:
                    conn.execute(db.text("ALTER TABLE attendance ADD COLUMN marked_by_admin BOOLEAN DEFAULT 0"))
                if "admin_note" not in att_cols:
                    conn.execute(db.text("ALTER TABLE attendance ADD COLUMN admin_note VARCHAR(255)"))
                conn.commit()
        except Exception:
            pass


ensure_db_schema()
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to continue."
login_manager.login_message_category = "info"


def parse_shift_times(timing_str: str | None) -> tuple[time, time, time]:
    """Parse shift start, 15-minute late exception cutoff, and shift end."""
    if not timing_str:
        return DEFAULT_SHIFT_START, DEFAULT_LATE_AFTER, DEFAULT_SHIFT_END
    try:
        parts = timing_str.split("(")[0].split("-")
        if len(parts) == 2:
            start_str = parts[0].strip()
            end_str = parts[1].strip()
            start_dt = datetime.strptime(start_str, "%I:%M %p")
            end_dt = datetime.strptime(end_str, "%I:%M %p")
            shift_start = start_dt.time()
            late_after = (start_dt + timedelta(minutes=15)).time()
            shift_end = end_dt.time()
            return shift_start, late_after, shift_end
    except Exception:
        pass
    return DEFAULT_SHIFT_START, DEFAULT_LATE_AFTER, DEFAULT_SHIFT_END


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(24), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(30), nullable=True, index=True)
    shift_timing = db.Column(db.String(40), nullable=True, default="10:00 AM - 07:00 PM")
    department = db.Column(db.String(80), nullable=False, default="Operations")
    job_title = db.Column(db.String(80), nullable=True, default="Employee")
    role = db.Column(db.String(20), nullable=False, default="employee", index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: now_ist())
    attendance = db.relationship("Attendance", back_populates="user", lazy="select")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def initials(self) -> str:
        parts = self.full_name.split()
        return "".join(part[0] for part in parts[:2]).upper() or "BW"

    def get_id(self) -> str:
        return str(self.id)


class Attendance(db.Model):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("user_id", "attendance_date", name="uq_attendance_user_date"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    attendance_date = db.Column(db.Date, nullable=False, index=True)
    checkin_at = db.Column(db.DateTime, nullable=False)
    checkout_at = db.Column(db.DateTime, nullable=True)
    checkin_latitude = db.Column(db.Float, nullable=False)
    checkin_longitude = db.Column(db.Float, nullable=False)
    checkout_latitude = db.Column(db.Float, nullable=True)
    checkout_longitude = db.Column(db.Float, nullable=True)
    break_start_at = db.Column(db.DateTime, nullable=True)
    break_end_at = db.Column(db.DateTime, nullable=True)
    exception_granted = db.Column(db.Boolean, nullable=False, default=False)
    marked_by_admin = db.Column(db.Boolean, nullable=False, default=False)
    admin_note = db.Column(db.String(255), nullable=True)
    user = db.relationship("User", back_populates="attendance")

    @property
    def shift_times(self) -> tuple[time, time, time]:
        timing = self.user.shift_timing if self.user else None
        return parse_shift_times(timing)

    @property
    def is_grace_period(self) -> bool:
        """True if arrival was within the 15-minute exception window after shift start."""
        shift_start, late_after, _ = self.shift_times
        return shift_start < self.checkin_at.time() <= late_after

    @property
    def is_late(self) -> bool:
        if self.exception_granted:
            return False
        shift_start, late_after, _ = self.shift_times
        return self.checkin_at.time() > late_after

    @property
    def status(self) -> str:
        if self.exception_granted:
            return "Present"
        shift_start, late_after, _ = self.shift_times
        return "Late" if self.checkin_at.time() > late_after else "Present"

    @property
    def status_label(self) -> str:
        if self.marked_by_admin:
            return "Present (Admin)" if self.status == "Present" or self.exception_granted else f"{self.status} (Admin)"
        if self.exception_granted:
            return "Present (Exception)"
        if self.is_grace_period:
            return "Present (15m Exception)"
        return self.status

    @property
    def break_display(self) -> str:
        if self.break_start_at and self.break_end_at:
            mins = max(1, int((self.break_end_at - self.break_start_at).total_seconds() // 60))
            return f"{self.break_start_at.strftime('%I:%M %p')} – {self.break_end_at.strftime('%I:%M %p')} ({mins}m)"
        elif self.break_start_at:
            return f"Started at {self.break_start_at.strftime('%I:%M %p')} (In progress)"
        return "Not taken"

    @property
    def break_in_progress(self) -> bool:
        return self.break_start_at is not None and self.break_end_at is None

    @property
    def duration_display(self) -> str:
        if not self.checkout_at:
            return "In progress"
        total_seconds = (self.checkout_at - self.checkin_at).total_seconds()
        break_seconds = 0
        if self.break_start_at and self.break_end_at:
            break_seconds = (self.break_end_at - self.break_start_at).total_seconds()
        elif self.break_start_at:
            break_seconds = 3600
        net_seconds = max(0, total_seconds - break_seconds)
        hours = int(net_seconds // 3600)
        minutes = int((net_seconds % 3600) // 60)
        return f"{hours}h {minutes}m"

    @property
    def gps_complete(self) -> bool:
        return self.checkin_latitude is not None and self.checkin_longitude is not None


def now_ist() -> datetime:
    """Return current India local time as a naive datetime stored consistently in SQLite."""
    return datetime.now(IST).replace(tzinfo=None, microsecond=0)


@login_manager.user_loader
def load_user(user_id: str):
    try:
        user = db.session.get(User, int(user_id))
        return user if user and user.active else None
    except (ValueError, TypeError):
        return None


@app.context_processor
def inject_globals():
    token = session_csrf_token()
    return {"csrf_token": token, "today": now_ist().date(), "now": now_ist(), "app_name": "Balaji Transports"}


def session_csrf_token() -> str:
    from flask import session
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


@app.before_request
def protect_post_requests():
    if request.method != "POST" or current_app.config.get("TESTING"):
        return None
    from flask import session
    supplied = request.headers.get("X-CSRFToken") or request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not expected or not supplied or not secrets.compare_digest(str(supplied), str(expected)):
        if request.is_json or request.path.startswith("/api/"):
            return jsonify({"ok": False, "message": "Your session token expired. Refresh the page and try again."}), 400
        abort(400, description="The form expired or could not be verified. Refresh the page and try again.")


def roles_required(*roles: str):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def team_query(query=None):
    query = query if query is not None else User.query
    if current_user.role == "manager":
        query = query.filter(User.department == current_user.department)
    return query


def attendance_query(query=None):
    query = query if query is not None else Attendance.query.join(User)
    if current_user.role == "manager":
        query = query.filter(User.department == current_user.department)
    elif current_user.role == "employee":
        query = query.filter(Attendance.user_id == current_user.id)
    return query


def parse_date(value: str | None, fallback: date | None = None) -> date | None:
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


def in_scope_user(user_id: int) -> User | None:
    user = db.session.get(User, user_id)
    if not user or not user.active:
        return None
    if current_user.role == "manager" and user.department != current_user.department:
        return None
    return user


def attendance_for_dashboard(selected_date: date):
    """Return dashboard attendance limited to the authenticated user's scope."""
    q = Attendance.query.join(User).filter(
        Attendance.attendance_date == selected_date,
        User.active.is_(True),
    )
    if current_user.role == "manager":
        q = q.filter(User.department == current_user.department)
    elif current_user.role == "employee":
        # Employees must never see other employees' attendance on their dashboard.
        q = q.filter(Attendance.user_id == current_user.id)
    return q.all()


def dashboard_data(selected_date: date) -> dict:
    if current_user.role == "employee":
        roster = [current_user._get_current_object()]
    else:
        roster = team_query(User.query.filter(User.active.is_(True))).all()
    records = attendance_for_dashboard(selected_date)
    present_ids = {row.user_id for row in records}
    present_count = len(present_ids)
    expected_workday = selected_date.weekday() < 5
    absent_count = max(0, len(roster) - present_count) if expected_workday else 0
    late_count = sum(1 for row in records if row.status == "Late")
    expected_count = len(roster) if expected_workday else 0
    attendance_rate = round((present_count / expected_count) * 100) if expected_count else 0

    trend_dates = []
    cursor = selected_date - timedelta(days=6)
    for offset in range(7):
        day = cursor + timedelta(days=offset)
        if current_user.role == "employee":
            total = Attendance.query.filter_by(user_id=current_user.id, attendance_date=day).count()
        else:
            trend_query = Attendance.query.join(User).filter(Attendance.attendance_date == day, User.active.is_(True))
            if current_user.role == "manager":
                trend_query = trend_query.filter(User.department == current_user.department)
            total = trend_query.count()
        trend_dates.append({"label": day.strftime("%b %d"), "present": total})

    recent = sorted(records, key=lambda item: item.checkin_at, reverse=True)[:8]
    return {
        "total_employees": len(roster), "present": present_count, "absent": absent_count,
        "late": late_count, "attendance_rate": attendance_rate, "is_workday": expected_workday,
        "trend": trend_dates, "recent": recent, "selected_date": selected_date,
        "records": records,
    }


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


def _complete_login(user: User):
    """Start an authenticated session and safely redirect to a local page."""
    login_user(user, remember=False, fresh=True)
    next_url = request.args.get("next", "")
    # Only allow local relative destinations to avoid open redirects.
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    flash(f"Welcome back, {user.full_name.split()[0]}.", "success")
    return redirect(url_for("dashboard"))


def _find_candidate_for_login(identifier: str) -> tuple[User | None, bool]:
    """Find workforce member by Gmail/email, phone number, login ID, or full name.
    Returns (candidate_user, is_ambiguous).
    """
    identifier = identifier.strip()
    if not identifier:
        return None, False

    # Block generated internal no-email placeholders from being used as login identifiers
    if identifier.lower().endswith("@no-email.invalid"):
        return None, False

    # 1. Email matching (case-insensitive) - standard for Admin & Manager (e.g. Gmail)
    if "@" in identifier:
        candidate = User.query.filter(
            User.active.is_(True),
            func.lower(User.email) == identifier.lower(),
        ).first()
        if candidate:
            return candidate, False

    # 2. Phone number matching (standard for field & operations employees)
    clean_phone = "".join(ch for ch in identifier if ch.isdigit())
    if len(clean_phone) >= 7:
        phone_matches = User.query.filter(
            User.active.is_(True),
            or_(
                User.phone == identifier,
                User.phone == clean_phone,
                User.phone.like(f"%{clean_phone}%"),
            ),
        ).all()
        if len(phone_matches) == 1:
            return phone_matches[0], False
        elif len(phone_matches) > 1:
            return None, True

    # 3. Employee ID matching (case-insensitive)
    candidate = User.query.filter(
        User.active.is_(True),
        func.lower(User.employee_id) == identifier.lower(),
    ).first()
    if candidate:
        return candidate, False

    # 4. Full name matching (case-insensitive)
    name_matches = User.query.filter(
        User.active.is_(True),
        func.lower(User.full_name) == identifier.lower(),
    ).all()
    if len(name_matches) == 1:
        return name_matches[0], False
    elif len(name_matches) > 1:
        return None, True

    # 5. Fallback email lookup without '@' check
    candidate = User.query.filter(
        User.active.is_(True),
        func.lower(User.email) == identifier.lower(),
    ).first()
    if candidate:
        return candidate, False

    return None, False


@app.route("/login", methods=["GET", "POST"])
def login():
    """Universal login portal for all workforce members: employees, managers, and administrators."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        identifier = (request.form.get("identifier") or request.form.get("email") or "").strip()
        password = request.form.get("password", "")
        candidate, ambiguous = _find_candidate_for_login(identifier)

        if ambiguous:
            flash("Multiple active accounts matched that name or number. Please use your exact mobile number, email, or login ID.", "danger")
        elif candidate and candidate.check_password(password):
            return _complete_login(candidate)
        else:
            flash("Invalid credentials or account is inactive. Please verify your details.", "danger")
    return render_template("login.html")


@app.route("/employee-login", methods=["GET", "POST"])
def employee_login():
    """Universal portal redirect for legacy employee login URLs."""
    if request.method == "POST":
        return login()
    return redirect(url_for("login"))


@app.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    today = now_ist().date()
    if current_user.role == "employee":
        today_record = Attendance.query.filter_by(user_id=current_user.id, attendance_date=today).first()
        history = Attendance.query.filter_by(user_id=current_user.id).order_by(Attendance.attendance_date.desc()).limit(30).all()
        fence = configured_geofence()
        return render_template(
            "dashboard.html",
            is_employee=True,
            record=today_record,
            history=history,
            geofence_configured=fence is not None,
            geofence_radius_meters=round(fence[2]) if fence else None,
            shift_timing=current_user.shift_timing or "10:00 AM - 07:00 PM",
            shift_start=DEFAULT_SHIFT_START.strftime("%I:%M %p"),
            late_after=DEFAULT_LATE_AFTER.strftime("%I:%M %p"),
            shift_end=DEFAULT_SHIFT_END.strftime("%I:%M %p"),
        )
    selected_date = parse_date(request.args.get("date"), today) or today
    selected_date = min(selected_date, today)
    data = dashboard_data(selected_date)
    return render_template("dashboard.html", is_employee=False, data=data)


@app.route("/attendance")
@login_required
def attendance_page():
    today_record = Attendance.query.filter_by(user_id=current_user.id, attendance_date=now_ist().date()).first()
    history = Attendance.query.filter_by(user_id=current_user.id).order_by(Attendance.attendance_date.desc()).limit(30).all()
    fence = configured_geofence()
    return render_template(
        "attendance.html",
        record=today_record,
        history=history,
        geofence_configured=fence is not None,
        geofence_radius_meters=round(fence[2]) if fence else None,
        shift_timing=current_user.shift_timing or "10:00 AM - 07:00 PM",
        shift_start=DEFAULT_SHIFT_START.strftime("%I:%M %p"),
        late_after=DEFAULT_LATE_AFTER.strftime("%I:%M %p"),
        shift_end=DEFAULT_SHIFT_END.strftime("%I:%M %p"),
    )


def parse_coordinates(payload: dict) -> tuple[float, float] | None:
    try:
        latitude = float(payload.get("latitude"))
        longitude = float(payload.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return latitude, longitude


def configured_geofence() -> tuple[float, float, float] | None:
    """Return (latitude, longitude, radius metres), or None if invalid/unconfigured."""
    try:
        latitude = float(current_app.config.get("GEOFENCE_LATITUDE", ""))
        longitude = float(current_app.config.get("GEOFENCE_LONGITUDE", ""))
        radius = float(current_app.config.get("GEOFENCE_RADIUS_METERS", "100"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(latitude) or not math.isfinite(longitude) or not math.isfinite(radius):
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180 or not 1 <= radius <= 100000:
        return None
    return latitude, longitude, radius


def distance_between_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the approximate great-circle distance between two coordinates."""
    earth_radius_m = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (math.sin(delta_phi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    a = min(1.0, max(0.0, a))
    return 2 * earth_radius_m * math.asin(math.sqrt(a))


def geofence_error(coordinates: tuple[float, float]):
    """Return (distance, error_response); an error_response is a Flask (body, status) pair."""
    fence = configured_geofence()
    if fence is None:
        return None, (jsonify(
            ok=False,
            message="Factory geofencing is not configured. Contact the administrator before recording attendance."
        ), 503)
    factory_lat, factory_lon, radius = fence
    distance = distance_between_meters(coordinates[0], coordinates[1], factory_lat, factory_lon)
    if distance > radius:
        return distance, (jsonify(
            ok=False,
            message=f"Outside the approved factory perimeter. You are approximately {round(distance)} m away; the allowed radius is {round(radius)} m.",
            distance_meters=round(distance),
            radius_meters=round(radius),
        ), 403)
    return distance, None


@app.post("/api/attendance/check-in")
@login_required
def check_in():
    payload = request.get_json(silent=True) or {}
    coordinates = parse_coordinates(payload)
    if not coordinates:
        return jsonify(ok=False, message="Valid GPS coordinates are required. Allow location access and try again."), 400
    distance, fence_error = geofence_error(coordinates)
    if fence_error:
        return fence_error
    now = now_ist()
    work_date = now.date()
    existing = Attendance.query.filter_by(user_id=current_user.id, attendance_date=work_date).first()
    if existing:
        if existing.checkout_at is None:
            return jsonify(ok=False, message="You are already checked in for today."), 409
        return jsonify(ok=False, message="A completed attendance record already exists for today."), 409
    latitude, longitude = coordinates
    record = Attendance(user_id=current_user.id, attendance_date=work_date, checkin_at=now,
                        checkin_latitude=latitude, checkin_longitude=longitude)
    db.session.add(record)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify(ok=False, message="Attendance could not be saved. Please try again."), 500
    return jsonify(ok=True, message=f"Check-in recorded at {now.strftime('%I:%M %p')}.",
                    checkin_at=now.strftime("%I:%M %p"), status=record.status,
                    distance_meters=round(distance) if distance is not None else None), 201


@app.post("/api/attendance/check-out")
@login_required
def check_out():
    payload = request.get_json(silent=True) or {}
    coordinates = parse_coordinates(payload)
    if not coordinates:
        return jsonify(ok=False, message="Valid GPS coordinates are required. Allow location access and try again."), 400
    distance, fence_error = geofence_error(coordinates)
    if fence_error:
        return fence_error
    now = now_ist()
    record = Attendance.query.filter_by(user_id=current_user.id, attendance_date=now.date()).first()
    if not record:
        return jsonify(ok=False, message="Check in before checking out."), 409
    if record.checkout_at:
        return jsonify(ok=False, message="You have already checked out today."), 409
    record.checkout_at = now
    record.checkout_latitude, record.checkout_longitude = coordinates
    db.session.commit()
    return jsonify(ok=True, message=f"Check-out recorded at {now.strftime('%I:%M %p')}.",
                    checkout_at=now.strftime("%I:%M %p"),
                    distance_meters=round(distance) if distance is not None else None), 200


@app.post("/api/attendance/break-start")
@login_required
def break_start():
    now = now_ist()
    record = Attendance.query.filter_by(user_id=current_user.id, attendance_date=now.date()).first()
    if not record:
        return jsonify(ok=False, message="You must check in before starting your break."), 409
    if record.checkout_at:
        return jsonify(ok=False, message="You have already completed your shift today."), 409
    if record.break_in_progress:
        return jsonify(ok=False, message="A break is already in progress."), 409
    record.break_start_at = now
    record.break_end_at = None
    db.session.commit()
    return jsonify(
        ok=True,
        message=f"1-hour break started at {now.strftime('%I:%M %p')}.",
        break_start=now.strftime("%I:%M %p"),
    ), 200


@app.post("/api/attendance/break-end")
@login_required
def break_end():
    now = now_ist()
    record = Attendance.query.filter_by(user_id=current_user.id, attendance_date=now.date()).first()
    if not record:
        return jsonify(ok=False, message="No active attendance record for today."), 409
    if not record.break_start_at or record.break_end_at is not None:
        return jsonify(ok=False, message="No active break in progress to resume from."), 409
    record.break_end_at = now
    db.session.commit()
    mins = max(1, int((now - record.break_start_at).total_seconds() // 60))
    return jsonify(
        ok=True,
        message=f"Break ended at {now.strftime('%I:%M %p')} ({mins} min buffer recorded). Resumed shift.",
        break_end=now.strftime("%I:%M %p"),
    ), 200


@app.post("/attendance/<int:record_id>/grant-exception")
@roles_required("admin", "manager")
def grant_attendance_exception(record_id: int):
    record = db.session.get(Attendance, record_id)
    if not record:
        abort(404)
    record.exception_granted = True
    db.session.commit()
    flash(f"15-minute late exception granted for {record.user.full_name}.", "success")
    return redirect(request.referrer or url_for("records"))


@app.post("/attendance/manual-mark")
@roles_required("admin", "manager")
def manual_mark_attendance():
    """Admin candidate-wise resolution: mark attendance for employees facing phone issues or outages."""
    user_id_raw = request.form.get("user_id", "").strip()
    date_str = request.form.get("attendance_date", "").strip()
    checkin_time_str = request.form.get("checkin_time", "").strip()
    checkout_time_str = request.form.get("checkout_time", "").strip()
    include_break = request.form.get("include_break") in {"1", "true", "on", "yes"}
    grant_exception = request.form.get("grant_exception") in {"1", "true", "on", "yes"}
    issue_reason = request.form.get("issue_reason", "").strip()
    custom_note = request.form.get("admin_note", "").strip()

    admin_note = custom_note or issue_reason or "Resolved by admin (phone broken / switched off / device issue)"

    try:
        user_id = int(user_id_raw)
    except (ValueError, TypeError):
        flash("Please select a candidate employee.", "danger")
        return redirect(url_for("records"))

    candidate = db.session.get(User, user_id)
    if not candidate:
        flash("Candidate employee record not found.", "danger")
        return redirect(url_for("records"))

    target_date = parse_date(date_str, now_ist().date()) or now_ist().date()

    # Parse check-in time
    try:
        if checkin_time_str:
            parts = [int(p) for p in checkin_time_str.split(":")[:2]]
            cin_time = time(parts[0], parts[1])
        else:
            cin_time = time(10, 0)
    except Exception:
        cin_time = time(10, 0)
    checkin_dt = datetime.combine(target_date, cin_time)

    # Parse check-out time
    checkout_dt = None
    if checkout_time_str:
        try:
            parts = [int(p) for p in checkout_time_str.split(":")[:2]]
            cout_time = time(parts[0], parts[1])
            checkout_dt = datetime.combine(target_date, cout_time)
        except Exception:
            checkout_dt = None

    # Parse 1-hour break buffer
    break_start_dt = None
    break_end_dt = None
    if include_break:
        b_start_str = request.form.get("break_start_time", "13:00").strip()
        b_end_str = request.form.get("break_end_time", "14:00").strip()
        try:
            sp = [int(p) for p in b_start_str.split(":")[:2]]
            break_start_dt = datetime.combine(target_date, time(sp[0], sp[1]))
        except Exception:
            break_start_dt = datetime.combine(target_date, time(13, 0))
        try:
            ep = [int(p) for p in b_end_str.split(":")[:2]]
            break_end_dt = datetime.combine(target_date, time(ep[0], ep[1]))
        except Exception:
            break_end_dt = datetime.combine(target_date, time(14, 0))

    fence = configured_geofence()
    lat = fence[0] if fence else 12.9716
    lon = fence[1] if fence else 77.5946

    # Update existing attendance or create new
    record = Attendance.query.filter_by(user_id=candidate.id, attendance_date=target_date).first()
    if record:
        record.checkin_at = checkin_dt
        if checkout_dt:
            record.checkout_at = checkout_dt
            record.checkout_latitude = lat
            record.checkout_longitude = lon
        if include_break:
            record.break_start_at = break_start_dt
            record.break_end_at = break_end_dt
        if grant_exception:
            record.exception_granted = True
        record.marked_by_admin = True
        record.admin_note = admin_note
    else:
        record = Attendance(
            user_id=candidate.id,
            attendance_date=target_date,
            checkin_at=checkin_dt,
            checkout_at=checkout_dt,
            checkin_latitude=lat,
            checkin_longitude=lon,
            checkout_latitude=lat if checkout_dt else None,
            checkout_longitude=lon if checkout_dt else None,
            break_start_at=break_start_dt,
            break_end_at=break_end_dt,
            exception_granted=grant_exception,
            marked_by_admin=True,
            admin_note=admin_note,
        )
        db.session.add(record)

    db.session.commit()
    flash(f"Attendance recorded for {candidate.full_name}. Issue resolved: {admin_note}", "success")
    return redirect(url_for("records"))


@app.post("/attendance/<int:record_id>/quick-checkout")
@roles_required("admin", "manager")
def quick_checkout(record_id: int):
    """Admin quick check-out for candidate whose phone died or went offline."""
    record = db.session.get(Attendance, record_id)
    if not record:
        abort(404)
    fence = configured_geofence()
    lat = fence[0] if fence else 12.9716
    lon = fence[1] if fence else 77.5946

    now = now_ist()
    record.checkout_at = now
    record.checkout_latitude = lat
    record.checkout_longitude = lon
    record.marked_by_admin = True
    if not record.admin_note:
        record.admin_note = "Check-out marked by admin (phone offline / battery dead)"
    db.session.commit()
    flash(f"Check-out recorded for candidate {record.user.full_name}.", "success")
    return redirect(request.referrer or url_for("records"))


@app.route("/employees")
@roles_required("admin", "manager")
def employees():
    search = request.args.get("q", "").strip()
    role = request.args.get("role", "").strip()
    selected_status = request.args.get("status", "active").strip().lower()
    if current_user.role == "admin":
        if selected_status == "disabled":
            base_query = User.query.filter(User.active.is_(False))
        elif selected_status == "all":
            base_query = User.query
        else:
            selected_status = "active"
            base_query = User.query.filter(User.active.is_(True))
    else:
        # Managers can only browse active people in their own department.
        selected_status = "active"
        base_query = User.query.filter(User.active.is_(True))
    query = team_query(base_query)
    if search:
        needle = f"%{search}%"
        query = query.filter(or_(
            User.full_name.ilike(needle),
            User.employee_id.ilike(needle),
            User.email.ilike(needle),
            User.phone.ilike(needle),
        ))
    if role in {"admin", "manager", "employee"}:
        query = query.filter(User.role == role)
    employee_rows = query.order_by(User.full_name.asc()).all()
    return render_template("employees.html", employees=employee_rows, search=search,
                           selected_role=role, selected_status=selected_status)


def _new_system_employee_id() -> str:
    """Generate a unique internal login ID when the company has no employee ID."""
    while True:
        candidate = f"SYS-{secrets.token_hex(4).upper()}"
        if not User.query.filter_by(employee_id=candidate).first():
            return candidate


def _new_placeholder_email() -> str:
    """Return a unique non-deliverable address for legacy non-null database schemas."""
    while True:
        candidate = f"no-email+{secrets.token_hex(8)}@no-email.invalid"
        if not User.query.filter_by(email=candidate).first():
            return candidate


def validate_employee_form(form, existing=None):
    """Validate employee fields. ID and job title are optional; phone is used for employees."""
    supplied_employee_id = form.get("employee_id", "").strip().upper()
    full_name = form.get("full_name", "").strip()
    supplied_email = form.get("email", "").strip().lower()
    phone = form.get("phone", "").strip()
    department = form.get("department", "").strip()
    job_title = form.get("job_title", "").strip()
    shift_timing = form.get("shift_timing", "").strip() or "10:00 AM - 07:00 PM"
    # Do not silently default a missing role: administrators must choose it.
    role = form.get("role", "").strip().lower()
    password = form.get("password", "")

    missing = []
    if not full_name:
        missing.append("full name")
    if not department:
        missing.append("department")
    # Job title is now optional per user request!
    if not role:
        missing.append("access role")
    if not existing and not password:
        missing.append("password")
    if missing:
        return None, "Complete the required fields: " + ", ".join(missing) + "."

    if len(full_name) > 120:
        return None, "Employee name is too long."
    if supplied_employee_id and len(supplied_employee_id) > 24:
        return None, "Employee ID is too long."
    if role not in {"admin", "manager", "employee"}:
        return None, "Select a valid role."

    # Validate phone for employee if provided
    if role == "employee" and phone:
        cleaned_phone = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
        if len(cleaned_phone) < 7 or len(cleaned_phone) > 16:
            return None, "Enter a valid phone number (at least 7 digits)."
        dup_phone_q = User.query.filter(User.phone == phone)
        if existing:
            dup_phone_q = dup_phone_q.filter(User.id != existing.id)
        if dup_phone_q.first():
            return None, "This phone number is already registered to another user."

    if role in {"admin", "manager"} and not supplied_email:
        return None, "A work email is required for Admin and Manager accounts because they sign in using email."

    if supplied_email and ("@" not in supplied_email or len(supplied_email) > 160 or any(ch.isspace() for ch in supplied_email)):
        return None, "Enter a valid email address or leave the email field blank."

    # Employees sign in with their full name, phone, or login ID, so active employee names must be unique.
    if role == "employee":
        duplicate_name_query = User.query.filter(
            User.role == "employee",
            User.active.is_(True),
            func.lower(User.full_name) == full_name.lower(),
        )
        if existing:
            duplicate_name_query = duplicate_name_query.filter(User.id != existing.id)
        if duplicate_name_query.first():
            return None, "Another active employee already has this full name. Add a middle name or initial so each employee can sign in unambiguously."

    # Automatically generate employee ID on creation if not manually supplied
    if existing:
        employee_id = existing.employee_id
    elif supplied_employee_id and not supplied_employee_id.startswith("(AUTO"):
        employee_id = supplied_employee_id
    else:
        employee_id = _new_system_employee_id()

    # SQLite schema currently requires a unique email value. When omitted, save a
    # non-deliverable placeholder internally; the UI displays phone for employees.
    if supplied_email:
        email = supplied_email
    elif existing and existing.email and not existing.email.endswith("@no-email.invalid"):
        email = existing.email
    else:
        email = _new_placeholder_email()

    for attr, value, label in (("employee_id", employee_id, "Employee ID"), ("email", email, "Email")):
        duplicate = User.query.filter(func.lower(getattr(User, attr)) == value.lower())
        if existing:
            duplicate = duplicate.filter(User.id != existing.id)
        if duplicate.first():
            return None, f"{label} is already in use."

    if not existing and len(password) < 8:
        return None, "Password must contain at least 8 characters."
    if existing and password and len(password) < 8:
        return None, "If changing the password, use at least 8 characters."

    return {
        "employee_id": employee_id,
        "full_name": full_name,
        "email": email,
        "phone": phone or (existing.phone if existing else ""),
        "shift_timing": shift_timing,
        "email_provided": bool(supplied_email),
        "employee_id_provided": bool(supplied_employee_id),
        "department": department,
        "job_title": job_title or "Employee",
        "role": role,
        "password": password,
    }, None


@app.route("/employees/new", methods=["GET", "POST"])
@roles_required("admin")
def employee_new():
    if request.method == "POST":
        values, error = validate_employee_form(request.form)
        if error:
            flash(error, "danger")
        else:
            user = User(employee_id=values["employee_id"], full_name=values["full_name"],
                        email=values["email"], phone=values["phone"],
                        shift_timing=values["shift_timing"], department=values["department"],
                        job_title=values["job_title"], role=values["role"], active=True)
            user.set_password(values["password"])
            db.session.add(user)
            db.session.commit()
            if user.role == "employee":
                contact_msg = f"Phone: {user.phone}" if user.phone else f"Login ID: {user.employee_id}"
                flash(
                    f"Account for {user.full_name} was created. Employee login ID: {user.employee_id}. {contact_msg}. "
                    f"Shift timing: {user.shift_timing}. "
                    "They can sign in at Employee Login using their phone number, full name, or assigned login ID and the temporary password. "
                    "Share the password securely.",
                    "success",
                )
            else:
                flash(
                    f"Account for {user.full_name} was created. They must sign in using their registered work email and password. "
                    "Share the password securely.",
                    "success",
                )
            return redirect(url_for("employees"))
    return render_template("employee_form.html", employee=None)


@app.route("/employees/<int:user_id>/edit", methods=["GET", "POST"])
@roles_required("admin")
def employee_edit(user_id: int):
    employee = db.session.get(User, user_id)
    if not employee:
        abort(404)
    if request.method == "POST":
        values, error = validate_employee_form(request.form, existing=employee)
        if error:
            flash(error, "danger")
        else:
            employee.employee_id = values["employee_id"]
            employee.full_name = values["full_name"]
            employee.email = values["email"]
            employee.phone = values["phone"]
            employee.shift_timing = values["shift_timing"]
            employee.department = values["department"]
            employee.job_title = values["job_title"]
            employee.role = values["role"]
            if values["password"]:
                employee.set_password(values["password"])
            db.session.commit()
            flash(f"Employee {employee.employee_id} was updated.", "success")
            return redirect(url_for("employees"))
    return render_template("employee_form.html", employee=employee)


@app.post("/employees/<int:user_id>/deactivate")
@roles_required("admin")
def employee_deactivate(user_id: int):
    employee = db.session.get(User, user_id)
    if not employee:
        abort(404)
    if employee.id == current_user.id:
        flash("You cannot deactivate your own account while signed in.", "danger")
    else:
        employee.active = False
        db.session.commit()
        flash(f"{employee.full_name} was disabled. Their login access is now blocked.", "success")
    return redirect(url_for("employees", status=request.args.get("status", "active")))


@app.post("/employees/<int:user_id>/activate")
@roles_required("admin")
def employee_activate(user_id: int):
    employee = db.session.get(User, user_id)
    if not employee:
        abort(404)
    employee.active = True
    db.session.commit()
    flash(f"{employee.full_name} was enabled and can sign in again.", "success")
    return redirect(url_for("employees", status=request.args.get("status", "disabled")))


def filtered_attendance_query():
    query = attendance_query(Attendance.query.join(User))
    start_date = parse_date(request.args.get("start"))
    end_date = parse_date(request.args.get("end"))
    employee_id = request.args.get("employee", "").strip()
    search = request.args.get("q", "").strip()
    if start_date:
        query = query.filter(Attendance.attendance_date >= start_date)
    if end_date:
        query = query.filter(Attendance.attendance_date <= end_date)
    if employee_id.isdigit() and current_user.role in {"admin", "manager"}:
        query = query.filter(Attendance.user_id == int(employee_id))
    if search:
        needle = f"%{search}%"
        query = query.filter(or_(User.full_name.ilike(needle), User.employee_id.ilike(needle)))
    return query.order_by(Attendance.attendance_date.desc(), Attendance.checkin_at.desc()), start_date, end_date, employee_id, search


@app.route("/records")
@login_required
def records():
    query, start_date, end_date, employee_filter, search = filtered_attendance_query()
    rows = query.limit(250).all()
    employee_rows = team_query(User.query.filter(User.active.is_(True))).order_by(User.full_name.asc()).all() if current_user.role in {"admin", "manager"} else []
    return render_template("records.html", records=rows, employees=employee_rows, start_date=start_date,
                           end_date=end_date, employee_filter=employee_filter, search=search)


@app.route("/reports")
@roles_required("admin", "manager")
def reports():
    start_date = parse_date(request.args.get("start"), now_ist().date().replace(day=1)) or now_ist().date().replace(day=1)
    end_date = parse_date(request.args.get("end"), default_report_end_date()) or default_report_end_date()
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    roster = team_query(User.query.filter(User.active.is_(True))).all()
    query = attendance_query(Attendance.query.join(User)).filter(Attendance.attendance_date >= start_date,
                                                                  Attendance.attendance_date <= end_date)
    rows = query.order_by(Attendance.attendance_date.desc(), Attendance.checkin_at.desc()).all()
    worked_days = max(0, (end_date - start_date).days + 1)
    expected_workdays = sum(1 for offset in range(worked_days) if (start_date + timedelta(days=offset)).weekday() < 5)
    summary_by_user = []
    for user in roster:
        user_rows = [row for row in rows if row.user_id == user.id]
        summary_by_user.append({"user": user, "present": len(user_rows),
                                "late": sum(1 for row in user_rows if row.status == "Late"),
                                "expected": expected_workdays})
    return render_template("reports.html", rows=rows, summary=summary_by_user,
                           start_date=start_date, end_date=end_date, total_records=len(rows))


def attendance_export_values(record: Attendance):
    """Return (display_login_datetime, login_status, logout_status).

    Actual timestamps remain stored in the database for audit purposes.
    Early arrivals are displayed/credited as the scheduled start time.
    Login through the 15-minute grace period or approved exception is Normal; after it is Late.
    Completed checkouts before shift end are Early; at/after shift end are On Time.
    A missing checkout has a blank logout status; it is never falsely marked On Time.
    """
    shift_start_time, late_after_time, shift_end_time = record.shift_times
    shift_start = datetime.combine(record.attendance_date, shift_start_time)
    late_after = datetime.combine(record.attendance_date, late_after_time)
    shift_end = datetime.combine(record.attendance_date, shift_end_time)

    display_login = shift_start if record.checkin_at < shift_start else record.checkin_at
    if record.exception_granted:
        login_status = "Normal"
    else:
        login_status = "Late" if record.checkin_at > late_after else "Normal"

    if record.checkout_at is None:
        # No checkout timestamp means no logout status can be determined yet.
        # Leave the cell blank instead of incorrectly claiming On Time.
        logout_status = ""
    elif record.checkout_at < shift_end:
        logout_status = "Early"
    else:
        logout_status = "On Time"

    return display_login, login_status, logout_status


def default_report_end_date() -> date:
    """Default reports to the latest completed workday. Explicit date filters can include today."""
    now = now_ist()
    today = now.date()
    if today.weekday() < 5 and now.time() >= DEFAULT_SHIFT_END:
        return today
    candidate = today - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def report_date_range():
    """Parse report dates and normalize reversed ranges."""
    today = now_ist().date()
    default_end = default_report_end_date()
    start_date = parse_date(request.args.get("start"), today.replace(day=1)) or today.replace(day=1)
    end_date = parse_date(request.args.get("end"), default_end) or default_end
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date


def report_attendance_rows(start_date: date, end_date: date):
    query = attendance_query(Attendance.query.join(User)).filter(
        Attendance.attendance_date >= start_date,
        Attendance.attendance_date <= end_date,
    )
    return query.order_by(Attendance.attendance_date.desc(), Attendance.checkin_at.desc()).all()


@app.route("/reports.csv")
@roles_required("admin", "manager")
def reports_csv():
    """Export attendance as CSV in the required eight-column order."""
    start_date, end_date = report_date_range()
    rows = report_attendance_rows(start_date, end_date)

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "Date",
        "Employee Name",
        "Department",
        "Role",
        "Login Status",
        "Login Time",
        "Logout Time",
        "Logout Status",
    ])

    for row in rows:
        login_time, login_status, logout_status = attendance_export_values(row)
        writer.writerow([
            row.attendance_date.strftime("%d-%m-%Y"),
            row.user.full_name,
            row.user.department,
            row.user.role.title(),
            login_status,
            login_time.strftime("%I:%M %p"),
            row.checkout_at.strftime("%I:%M %p") if row.checkout_at else "",
            logout_status,
        ])

    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=balaji-attendance-{start_date}-to-{end_date}.csv"
    )
    return response


@app.route("/reports.xlsx")
@roles_required("admin", "manager")
def reports_xlsx():
    """Export attendance as an eight-column Excel workbook with status colors."""
    start_date, end_date = report_date_range()
    rows = report_attendance_rows(start_date, end_date)

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    worksheet = workbook.add_worksheet("Attendance")

    header_format = workbook.add_format({
        "bold": True,
        "font_color": "#FFFFFF",
        "bg_color": "#17365D",
        "border": 1,
        "align": "center",
        "valign": "vcenter",
    })
    date_format = workbook.add_format({"num_format": "dd-mm-yyyy"})
    time_format = workbook.add_format({"num_format": "hh:mm AM/PM"})
    normal_format = workbook.add_format({
        "font_color": "#166534",
        "bg_color": "#DCFCE7",
        "bold": True,
    })
    late_format = workbook.add_format({
        "font_color": "#B91C1C",
        "bg_color": "#FEE2E2",
        "bold": True,
    })
    on_time_format = workbook.add_format({
        "font_color": "#166534",
        "bg_color": "#DCFCE7",
        "bold": True,
    })
    early_format = workbook.add_format({
        "font_color": "#B91C1C",
        "bg_color": "#FEE2E2",
        "bold": True,
    })
    headers = [
        "Date",
        "Employee Name",
        "Department",
        "Role",
        "Login Status",
        "Login Time",
        "Logout Time",
        "Logout Status",
    ]
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)

    worksheet.set_column("A:A", 14)
    worksheet.set_column("B:B", 24)
    worksheet.set_column("C:C", 22)
    worksheet.set_column("D:D", 14)
    worksheet.set_column("E:E", 16)
    worksheet.set_column("F:F", 15)
    worksheet.set_column("G:G", 15)
    worksheet.set_column("H:H", 18)
    worksheet.set_row(0, 24)
    worksheet.freeze_panes(1, 0)

    for excel_row, record in enumerate(rows, start=1):
        login_time, login_status, logout_status = attendance_export_values(record)

        worksheet.write_datetime(
            excel_row,
            0,
            datetime.combine(record.attendance_date, time(0, 0)),
            date_format,
        )
        worksheet.write_string(excel_row, 1, record.user.full_name)
        worksheet.write_string(excel_row, 2, record.user.department)
        worksheet.write_string(excel_row, 3, record.user.role.title())

        login_format = normal_format if login_status == "Normal" else late_format
        worksheet.write_string(excel_row, 4, login_status, login_format)
        worksheet.write_datetime(excel_row, 5, login_time, time_format)

        if record.checkout_at is not None:
            worksheet.write_datetime(
                excel_row, 6, record.checkout_at, time_format
            )
        else:
            worksheet.write_blank(excel_row, 6, None)

        logout_formats = {
            "On Time": on_time_format,
            "Early": early_format,
        }
        # Blank status when no checkout was recorded. Do not fabricate a result.
        worksheet.write_string(
            excel_row,
            7,
            logout_status,
            logout_formats.get(logout_status),
        )

    worksheet.autofilter(0, 0, len(rows), len(headers) - 1)
    workbook.close()
    output.seek(0)

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response.headers["Content-Disposition"] = (
        f"attachment; filename=balaji-attendance-{start_date}-to-{end_date}.xlsx"
    )
    return response


def build_daily_owner_report(report_day: date) -> list[dict]:
    """Build a compact owner report for all active non-admin workforce accounts.

    Missing attendance on a past weekday is marked Absent. On today's report, an
    employee is not marked absent until the scheduled shift end. Missing check-out
    remains Pending and is never incorrectly marked On Time.
    """
    now = now_ist()
    roster = (
        User.query.filter(User.active.is_(True), User.role != "admin")
        .order_by(User.full_name.asc())
        .all()
    )
    attendance = (
        Attendance.query.join(User)
        .filter(
            Attendance.attendance_date == report_day,
            User.active.is_(True),
            User.role != "admin",
        )
        .all()
    )
    by_user = {row.user_id: row for row in attendance}
    output = []

    for user in roster:
        record = by_user.get(user.id)
        if record:
            _, login_status, logout_status = attendance_export_values(record)
            if record.checkout_at is None:
                logout_status = "Pending"
        else:
            if report_day > now.date():
                login_status, logout_status = "Upcoming", "—"
            elif report_day.weekday() >= 5:
                login_status, logout_status = "Non-working day", "—"
            elif report_day < now.date() or now.time() >= DEFAULT_SHIFT_END:
                login_status, logout_status = "Absent", "—"
            else:
                login_status, logout_status = "Not checked in yet", "—"

        output.append({
            "employee_name": user.full_name,
            "login_status": login_status,
            "logout_status": logout_status,
        })
    return output


@app.route("/reports/daily")
@roles_required("admin")
def daily_owner_report():
    """Display a simple daily attendance summary for the owner/admin."""
    report_day = parse_date(request.args.get("date"), now_ist().date()) or now_ist().date()
    rows = build_daily_owner_report(report_day)
    return render_template(
        "daily_report.html",
        report_day=report_day,
        rows=rows,
        present_count=sum(row["login_status"] in {"Normal", "Late"} for row in rows),
        late_count=sum(row["login_status"] == "Late" for row in rows),
        absent_count=sum(row["login_status"] == "Absent" for row in rows),
        pending_checkout_count=sum(row["logout_status"] == "Pending" for row in rows),
    )


@app.route("/reports/daily.csv")
@roles_required("admin")
def daily_owner_report_csv():
    """Download the owner daily report as a compact CSV file."""
    report_day = parse_date(request.args.get("date"), now_ist().date()) or now_ist().date()
    rows = build_daily_owner_report(report_day)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Employee Name", "Login Status", "Logout Status"])
    for row in rows:
        writer.writerow([
            row["employee_name"],
            row["login_status"],
            row["logout_status"],
        ])
    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f"attachment; filename=balaji-daily-attendance-{report_day}.csv"
    return response


@app.errorhandler(403)
def forbidden(error):
    return render_template("errors/403.html"), 403


@app.errorhandler(404)
def not_found(error):
    return render_template("errors/404.html"), 404


@app.errorhandler(400)
def bad_request(error):
    message = getattr(error, "description", "The request could not be completed.")
    return render_template("errors/400.html", message=message), 400


with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG") == "1")
