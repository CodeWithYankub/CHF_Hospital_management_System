from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from functools import wraps

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)

# Production configuration is supplied through environment variables.
secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    secret_key = "development-only-change-me"
app.config["SECRET_KEY"] = secret_key

database_url = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'chf_hms.db')}")
# Some hosting providers still return the old postgres:// scheme.
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "0") == "1"

# Correct HTTPS and client-address handling when hosted behind a reverse proxy.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to continue."


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(UserMixin, TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(40), nullable=False, default="records")
    active = db.Column(db.Boolean, default=True, nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self) -> bool:
        return self.active


class Patient(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_no = db.Column(db.String(30), unique=True, index=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    sex = db.Column(db.String(20), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    phone = db.Column(db.String(30))
    address = db.Column(db.String(255))
    district = db.Column(db.String(100))
    next_of_kin = db.Column(db.String(120))
    next_of_kin_phone = db.Column(db.String(30))
    blood_group = db.Column(db.String(10))
    allergies = db.Column(db.Text)
    sickle_cell_status = db.Column(db.String(30))
    free_care_category = db.Column(db.String(50), default="Paying")

    visits = db.relationship("Visit", backref="patient", lazy=True, cascade="all, delete-orphan")
    invoices = db.relationship("Invoice", backref="patient", lazy=True, cascade="all, delete-orphan")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self):
        if not self.date_of_birth:
            return "—"
        today = date.today()
        years = today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )
        return years


class Visit(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    visit_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    department = db.Column(db.String(80), nullable=False, default="Outpatient")
    complaint = db.Column(db.Text)
    diagnosis = db.Column(db.Text)
    treatment_plan = db.Column(db.Text)
    clinician = db.Column(db.String(120))
    status = db.Column(db.String(30), default="Open")

    vitals = db.relationship("VitalSign", backref="visit", uselist=False, cascade="all, delete-orphan")


class VitalSign(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    visit_id = db.Column(db.Integer, db.ForeignKey("visit.id"), nullable=False, unique=True)
    temperature = db.Column(db.Float)
    systolic = db.Column(db.Integer)
    diastolic = db.Column(db.Integer)
    pulse = db.Column(db.Integer)
    respiratory_rate = db.Column(db.Integer)
    oxygen_saturation = db.Column(db.Integer)
    weight_kg = db.Column(db.Float)
    height_cm = db.Column(db.Float)


class Medication(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    strength = db.Column(db.String(80))
    dosage_form = db.Column(db.String(80))
    batch_no = db.Column(db.String(80))
    expiry_date = db.Column(db.Date)
    quantity = db.Column(db.Integer, default=0, nullable=False)
    reorder_level = db.Column(db.Integer, default=10, nullable=False)
    unit_cost = db.Column(db.Numeric(12, 2), default=0)
    selling_price = db.Column(db.Numeric(12, 2), default=0)
    source = db.Column(db.String(120), default="Purchased")

    @property
    def low_stock(self) -> bool:
        return self.quantity <= self.reorder_level


class Invoice(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_no = db.Column(db.String(30), unique=True, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    amount_paid = db.Column(db.Numeric(12, 2), default=0, nullable=False)
    payment_status = db.Column(db.String(30), default="Unpaid")
    payment_method = db.Column(db.String(40))
    waived_reason = db.Column(db.String(255))

    @property
    def balance(self):
        return Decimal(self.amount or 0) - Decimal(self.amount_paid or 0)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    action = db.Column(db.String(120), nullable=False)
    entity = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles and current_user.role != "admin":
                flash("You do not have permission to perform that action.", "danger")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)

        return wrapped

    return decorator


def add_audit(action: str, entity: str, entity_id: int | None = None, details: str = "") -> None:
    db.session.add(
        AuditLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details,
        )
    )


def generate_number(prefix: str, model, field_name: str) -> str:
    year = datetime.utcnow().year
    count = model.query.count() + 1
    candidate = f"{prefix}-{year}-{count:06d}"
    while model.query.filter(getattr(model, field_name) == candidate).first():
        count += 1
        candidate = f"{prefix}-{year}-{count:06d}"
    return candidate


@app.route("/")
def index():
    return redirect(url_for("dashboard") if current_user.is_authenticated else url_for("login"))


@app.route("/health")
def health():
    """Health-check endpoint used by web hosting platforms."""
    return jsonify(status="ok", application="CHF-HMS"), 200


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password) and user.active:
            login_user(user)
            add_audit("LOGIN", "User", user.id)
            db.session.commit()
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    add_audit("LOGOUT", "User", current_user.id)
    db.session.commit()
    logout_user()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    today_start = datetime.combine(date.today(), datetime.min.time())
    stats = {
        "patients": Patient.query.count(),
        "visits_today": Visit.query.filter(Visit.visit_date >= today_start).count(),
        "open_visits": Visit.query.filter_by(status="Open").count(),
        "low_stock": Medication.query.filter(Medication.quantity <= Medication.reorder_level).count(),
        "unpaid": db.session.query(db.func.coalesce(db.func.sum(Invoice.amount - Invoice.amount_paid), 0))
        .filter(Invoice.payment_status != "Paid")
        .scalar(),
        "revenue_today": db.session.query(db.func.coalesce(db.func.sum(Invoice.amount_paid), 0))
        .filter(Invoice.updated_at >= today_start)
        .scalar(),
    }
    recent_visits = Visit.query.order_by(Visit.visit_date.desc()).limit(8).all()
    low_stock_items = Medication.query.filter(Medication.quantity <= Medication.reorder_level).order_by(Medication.quantity).limit(8).all()
    return render_template("dashboard.html", stats=stats, recent_visits=recent_visits, low_stock_items=low_stock_items)


@app.route("/patients")
@login_required
def patients():
    q = request.args.get("q", "").strip()
    query = Patient.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                Patient.patient_no.ilike(like),
                Patient.first_name.ilike(like),
                Patient.last_name.ilike(like),
                Patient.phone.ilike(like),
            )
        )
    return render_template("patients.html", patients=query.order_by(Patient.created_at.desc()).all(), q=q)


@app.route("/patients/new", methods=["GET", "POST"])
@roles_required("admin", "records", "nurse", "doctor")
def patient_new():
    if request.method == "POST":
        dob_text = request.form.get("date_of_birth")
        patient = Patient(
            patient_no=generate_number("CHF", Patient, "patient_no"),
            first_name=request.form["first_name"].strip(),
            last_name=request.form["last_name"].strip(),
            sex=request.form["sex"],
            date_of_birth=datetime.strptime(dob_text, "%Y-%m-%d").date() if dob_text else None,
            phone=request.form.get("phone", "").strip(),
            address=request.form.get("address", "").strip(),
            district=request.form.get("district", "").strip(),
            next_of_kin=request.form.get("next_of_kin", "").strip(),
            next_of_kin_phone=request.form.get("next_of_kin_phone", "").strip(),
            blood_group=request.form.get("blood_group", "").strip(),
            allergies=request.form.get("allergies", "").strip(),
            sickle_cell_status=request.form.get("sickle_cell_status", "").strip(),
            free_care_category=request.form.get("free_care_category", "Paying"),
        )
        db.session.add(patient)
        db.session.flush()
        add_audit("CREATE", "Patient", patient.id, patient.patient_no)
        db.session.commit()
        flash(f"Patient registered successfully: {patient.patient_no}", "success")
        return redirect(url_for("patient_detail", patient_id=patient.id))
    return render_template("patient_form.html")


@app.route("/patients/<int:patient_id>")
@login_required
def patient_detail(patient_id):
    patient = db.get_or_404(Patient, patient_id)
    return render_template("patient_detail.html", patient=patient)


@app.route("/patients/<int:patient_id>/visits/new", methods=["GET", "POST"])
@roles_required("admin", "records", "nurse", "doctor")
def visit_new(patient_id):
    patient = db.get_or_404(Patient, patient_id)
    if request.method == "POST":
        visit = Visit(
            patient_id=patient.id,
            department=request.form.get("department", "Outpatient"),
            complaint=request.form.get("complaint", "").strip(),
            diagnosis=request.form.get("diagnosis", "").strip(),
            treatment_plan=request.form.get("treatment_plan", "").strip(),
            clinician=request.form.get("clinician", current_user.full_name).strip(),
            status=request.form.get("status", "Open"),
        )
        db.session.add(visit)
        db.session.flush()
        vitals = VitalSign(
            visit_id=visit.id,
            temperature=float(request.form["temperature"]) if request.form.get("temperature") else None,
            systolic=int(request.form["systolic"]) if request.form.get("systolic") else None,
            diastolic=int(request.form["diastolic"]) if request.form.get("diastolic") else None,
            pulse=int(request.form["pulse"]) if request.form.get("pulse") else None,
            respiratory_rate=int(request.form["respiratory_rate"]) if request.form.get("respiratory_rate") else None,
            oxygen_saturation=int(request.form["oxygen_saturation"]) if request.form.get("oxygen_saturation") else None,
            weight_kg=float(request.form["weight_kg"]) if request.form.get("weight_kg") else None,
            height_cm=float(request.form["height_cm"]) if request.form.get("height_cm") else None,
        )
        db.session.add(vitals)
        add_audit("CREATE", "Visit", visit.id, f"Patient {patient.patient_no}")
        db.session.commit()
        flash("Visit saved successfully.", "success")
        return redirect(url_for("patient_detail", patient_id=patient.id))
    return render_template("visit_form.html", patient=patient)


@app.route("/pharmacy")
@login_required
def pharmacy():
    items = Medication.query.order_by(Medication.name).all()
    return render_template("pharmacy.html", items=items)


@app.route("/pharmacy/new", methods=["GET", "POST"])
@roles_required("admin", "pharmacist")
def medication_new():
    if request.method == "POST":
        expiry = request.form.get("expiry_date")
        medication = Medication(
            name=request.form["name"].strip(),
            strength=request.form.get("strength", "").strip(),
            dosage_form=request.form.get("dosage_form", "").strip(),
            batch_no=request.form.get("batch_no", "").strip(),
            expiry_date=datetime.strptime(expiry, "%Y-%m-%d").date() if expiry else None,
            quantity=int(request.form.get("quantity", 0)),
            reorder_level=int(request.form.get("reorder_level", 10)),
            unit_cost=Decimal(request.form.get("unit_cost", "0") or "0"),
            selling_price=Decimal(request.form.get("selling_price", "0") or "0"),
            source=request.form.get("source", "Purchased"),
        )
        db.session.add(medication)
        db.session.flush()
        add_audit("CREATE", "Medication", medication.id, medication.name)
        db.session.commit()
        flash("Medication added to inventory.", "success")
        return redirect(url_for("pharmacy"))
    return render_template("medication_form.html")


@app.route("/pharmacy/<int:item_id>/adjust", methods=["POST"])
@roles_required("admin", "pharmacist")
def medication_adjust(item_id):
    item = db.get_or_404(Medication, item_id)
    adjustment = int(request.form.get("adjustment", 0))
    reason = request.form.get("reason", "Stock adjustment").strip()
    new_quantity = item.quantity + adjustment
    if new_quantity < 0:
        flash("Stock cannot be reduced below zero.", "danger")
    else:
        old = item.quantity
        item.quantity = new_quantity
        add_audit("ADJUST_STOCK", "Medication", item.id, f"{old} to {new_quantity}; {reason}")
        db.session.commit()
        flash("Stock updated.", "success")
    return redirect(url_for("pharmacy"))


@app.route("/billing")
@login_required
def billing():
    invoices = Invoice.query.order_by(Invoice.created_at.desc()).all()
    total_billed = db.session.query(db.func.coalesce(db.func.sum(Invoice.amount), 0)).scalar()
    total_paid = db.session.query(db.func.coalesce(db.func.sum(Invoice.amount_paid), 0)).scalar()
    return render_template("billing.html", invoices=invoices, total_billed=total_billed, total_paid=total_paid)


@app.route("/billing/new", methods=["GET", "POST"])
@roles_required("admin", "cashier", "records")
def invoice_new():
    patients_list = Patient.query.order_by(Patient.first_name, Patient.last_name).all()
    if request.method == "POST":
        amount = Decimal(request.form["amount"])
        paid = Decimal(request.form.get("amount_paid", "0") or "0")
        status = "Paid" if paid >= amount else ("Partially Paid" if paid > 0 else "Unpaid")
        invoice = Invoice(
            invoice_no=generate_number("INV", Invoice, "invoice_no"),
            patient_id=int(request.form["patient_id"]),
            description=request.form["description"].strip(),
            amount=amount,
            amount_paid=paid,
            payment_status=status,
            payment_method=request.form.get("payment_method", "Cash"),
            waived_reason=request.form.get("waived_reason", "").strip(),
        )
        db.session.add(invoice)
        db.session.flush()
        add_audit("CREATE", "Invoice", invoice.id, invoice.invoice_no)
        db.session.commit()
        flash("Invoice created.", "success")
        return redirect(url_for("billing"))
    return render_template("invoice_form.html", patients=patients_list)


@app.route("/billing/<int:invoice_id>/pay", methods=["POST"])
@roles_required("admin", "cashier")
def invoice_pay(invoice_id):
    invoice = db.get_or_404(Invoice, invoice_id)
    payment = Decimal(request.form.get("payment", "0") or "0")
    if payment <= 0:
        flash("Enter a payment greater than zero.", "danger")
    elif payment > invoice.balance:
        flash("Payment cannot exceed the outstanding balance.", "danger")
    else:
        invoice.amount_paid = Decimal(invoice.amount_paid or 0) + payment
        invoice.payment_method = request.form.get("payment_method", invoice.payment_method)
        invoice.payment_status = "Paid" if invoice.amount_paid >= invoice.amount else "Partially Paid"
        add_audit("PAYMENT", "Invoice", invoice.id, f"Payment: {payment}")
        db.session.commit()
        flash("Payment recorded.", "success")
    return redirect(url_for("billing"))


@app.route("/users")
@roles_required("admin")
def users():
    return render_template("users.html", users=User.query.order_by(User.full_name).all())


@app.route("/users/new", methods=["GET", "POST"])
@roles_required("admin")
def user_new():
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        if User.query.filter_by(username=username).first():
            flash("That username already exists.", "danger")
            return render_template("user_form.html")
        user = User(
            full_name=request.form["full_name"].strip(),
            username=username,
            role=request.form["role"],
        )
        user.set_password(request.form["password"])
        db.session.add(user)
        db.session.flush()
        add_audit("CREATE", "User", user.id, username)
        db.session.commit()
        flash("User account created.", "success")
        return redirect(url_for("users"))
    return render_template("user_form.html")


@app.route("/audit")
@roles_required("admin")
def audit():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(300).all()
    user_map = {u.id: u.full_name for u in User.query.all()}
    return render_template("audit.html", logs=logs, user_map=user_map)


@app.template_filter("money")
def money(value):
    return f"SLE {Decimal(value or 0):,.2f}"


def seed_database():
    db.create_all()
    if not User.query.first():
        admin_username = os.environ.get("ADMIN_USERNAME", "admin").strip().lower()
        admin_password = os.environ.get("ADMIN_PASSWORD", "ChangeMe123!")
        admin = User(full_name="System Administrator", username=admin_username, role="admin")
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.commit()


with app.app_context():
    seed_database()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
