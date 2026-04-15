"""
reminders.py — Flask blueprint for medicine reminders.

Dependencies to install:
    pip install apscheduler twilio flask-mail python-dotenv

Environment variables required (add to your .env):
    # Email (SMTP)
    MAIL_SERVER=smtp.gmail.com
    MAIL_PORT=587
    MAIL_USERNAME=your@gmail.com
    MAIL_PASSWORD=your_app_password          # Gmail App Password, NOT your login password
    MAIL_FROM=your@gmail.com

    # WhatsApp via Twilio
    TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    TWILIO_WHATSAPP_FROM=whatsapp:+14155238886  # Twilio sandbox or your approved number

    # Scheduler timezone (optional, default UTC)
    SCHEDULER_TIMEZONE=Asia/Kolkata
"""

import os
import logging
from datetime import datetime, date
from functools import wraps

from flask import Blueprint, request, jsonify
import jwt

# ── APScheduler ───────────────────────────────────────────────────────────────
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore
import pytz

# ── Email ─────────────────────────────────────────────────────────────────────
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── WhatsApp via Twilio ───────────────────────────────────────────────────────
try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    logging.warning("Twilio not installed. WhatsApp reminders will be disabled. Run: pip install twilio")

# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

reminders_bp = Blueprint("reminders", __name__, url_prefix="/api/reminders")

JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-this")
SCHEDULER_TIMEZONE = os.getenv("SCHEDULER_TIMEZONE", "UTC")

# ── Scheduler singleton ───────────────────────────────────────────────────────

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None or not _scheduler.running:
        tz = pytz.timezone(SCHEDULER_TIMEZONE)
        _scheduler = BackgroundScheduler(
            jobstores={"default": MemoryJobStore()},
            timezone=tz,
        )
        _scheduler.start()
        logger.info("APScheduler started (tz=%s)", SCHEDULER_TIMEZONE)
    return _scheduler


def get_db():
    """Return the pulsesync MongoDB database, connecting the same way as user.py."""
    from pymongo import MongoClient
    client = MongoClient('mongodb://localhost:27017/')
    return client['pulsesync']


# ── Auth decorator ────────────────────────────────────────────────────────────

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "")
        if not token:
            return jsonify({"error": "Missing authorization token"}), 401
        try:
            if token.startswith("Bearer "):
                token = token[7:]
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            request.user_id = data["user_id"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


# ── Notification helpers ──────────────────────────────────────────────────────

def _build_email_html(medicine_name: str, dosage_note: str, time_label: str) -> str:
    """Build a clean HTML email body for the reminder."""
    dosage_line = f"<p style='margin:6px 0;color:#374151;font-size:15px;'><b>Dosage:</b> {dosage_note}</p>" if dosage_note else ""
    return f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:480px;margin:auto;background:#fff;border-radius:16px;overflow:hidden;border:1px solid #e5e7eb;">
      <div style="background:linear-gradient(135deg,#0f172a,#1e293b);padding:24px 28px;">
        <p style="margin:0;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:rgba(255,255,255,.4);font-weight:600;">Medicine Reminder</p>
        <h1 style="margin:4px 0 0;color:white;font-size:22px;font-weight:800;letter-spacing:-0.02em;">💊 Time for {medicine_name}</h1>
      </div>
      <div style="padding:24px 28px;">
        <p style="margin:0 0 6px;color:#6b7280;font-size:13px;text-transform:uppercase;letter-spacing:.08em;font-weight:600;">Scheduled time</p>
        <p style="margin:0 0 16px;color:#111827;font-size:17px;font-weight:700;">{time_label}</p>
        {dosage_line}
        <div style="margin-top:20px;padding:14px 16px;background:#f0fdf4;border-radius:10px;border:1px solid #bbf7d0;">
          <p style="margin:0;color:#166534;font-size:13px;line-height:1.6;">Stay consistent with your medication schedule for the best results. Take it with water and follow your doctor's instructions. ✅</p>
        </div>
      </div>
      <div style="padding:14px 28px;background:#f9fafb;border-top:1px solid #f3f4f6;">
        <p style="margin:0;font-size:11px;color:#9ca3af;line-height:1.6;">This is an automated reminder. Always follow your doctor's prescription. Do not adjust dosage without medical advice.</p>
      </div>
    </div>
    """


def send_email_reminder(to_email: str, medicine_name: str, dosage_note: str, time_label: str):
    """Send a reminder email via SMTP."""
    mail_server   = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    mail_port     = int(os.getenv("MAIL_PORT", "587"))
    mail_user     = os.getenv("MAIL_USERNAME", "")
    mail_password = os.getenv("MAIL_PASSWORD", "")
    mail_from     = os.getenv("MAIL_FROM", mail_user)

    if not mail_user or not mail_password:
        logger.warning("Email credentials not configured; skipping email reminder.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"💊 Reminder: Take your {medicine_name}"
    msg["From"]    = mail_from
    msg["To"]      = to_email

    html = _build_email_html(medicine_name, dosage_note, time_label)
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(mail_server, mail_port) as server:
            server.ehlo()
            server.starttls()
            server.login(mail_user, mail_password)
            server.sendmail(mail_from, to_email, msg.as_string())
        logger.info("Email reminder sent to %s for %s", to_email, medicine_name)
    except Exception as e:
        logger.error("Failed to send email reminder: %s", str(e))


def send_whatsapp_reminder(to_number: str, medicine_name: str, dosage_note: str, time_label: str):
    """Send a WhatsApp message via Twilio."""
    if not TWILIO_AVAILABLE:
        logger.warning("Twilio not installed; skipping WhatsApp reminder.")
        return

    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    if not account_sid or not auth_token:
        logger.warning("Twilio credentials not configured; skipping WhatsApp reminder.")
        return

    # Ensure E.164 format with whatsapp: prefix
    if not to_number.startswith("whatsapp:"):
        to_number = f"whatsapp:{to_number}"

    dosage_line = f"\n📋 *Dosage:* {dosage_note}" if dosage_note else ""
    body = (
        f"💊 *Medicine Reminder*\n\n"
        f"It's time to take your *{medicine_name}*!\n"
        f"🕐 *Scheduled:* {time_label}"
        f"{dosage_line}\n\n"
        f"Stay consistent with your medication for the best results. ✅\n\n"
        f"_This is an automated reminder. Always follow your doctor's prescription._"
    )

    try:
        client = TwilioClient(account_sid, auth_token)
        message = client.messages.create(body=body, from_=from_number, to=to_number)
        logger.info("WhatsApp reminder sent to %s (SID=%s) for %s", to_number, message.sid, medicine_name)
    except Exception as e:
        logger.error("Failed to send WhatsApp reminder: %s", str(e))


def dispatch_reminder(reminder_doc: dict, time_label: str):
    """
    Called by APScheduler for each scheduled slot.
    reminder_doc is the MongoDB document (or dict) for the reminder.
    """
    medicine_name = reminder_doc.get("medicine_name", "your medicine")
    dosage_note   = reminder_doc.get("dosage_note", "")
    notify_via    = reminder_doc.get("notify_via", "email")
    email         = reminder_doc.get("contact_email", "")
    whatsapp      = reminder_doc.get("contact_whatsapp", "")
    print("DEBUG notify_via:", notify_via)
    print("DEBUG whatsapp:", whatsapp)
    # Check date window
    today_str = date.today().isoformat()
    start = reminder_doc.get("start_date", today_str)
    end   = reminder_doc.get("end_date", today_str)
    if not (start <= today_str <= end):
        logger.debug("Reminder outside date window, skipping.")
        return

    if notify_via in ("email", "both") and email:
        send_email_reminder(email, medicine_name, dosage_note, time_label)
    if notify_via in ("whatsapp", "both") and whatsapp:
        send_whatsapp_reminder(whatsapp, medicine_name, dosage_note, time_label)


# ── Scheduler job management ──────────────────────────────────────────────────

def _day_abbr_to_cron(days: list[str]) -> str:
    """Convert ['Mon','Tue','Sun'] → 'mon,tue,sun' for APScheduler CronTrigger."""
    return ",".join(d.lower() for d in days) if days else "*"


def schedule_reminder_jobs(reminder_id: str, reminder_doc: dict):
    """
    Create one APScheduler cron job per time slot in the reminder.
    Job IDs follow the pattern: reminder_{reminder_id}_{slot_index}
    """
    scheduler = get_scheduler()
    times        = reminder_doc.get("times", [])
    frequency    = reminder_doc.get("frequency", "daily")
    days_of_week = reminder_doc.get("days_of_week", [])

    cron_days = "*" if frequency == "daily" else _day_abbr_to_cron(days_of_week)

    for i, slot in enumerate(times):
        time_str  = slot.get("time", "08:00")   # HH:mm
        time_label = f"{slot.get('label', '')} ({time_str})"

        try:
            hour, minute = map(int, time_str.split(":"))
        except ValueError:
            logger.warning("Invalid time '%s' for reminder %s, skipping slot.", time_str, reminder_id)
            continue

        job_id = f"reminder_{reminder_id}_{i}"

        # Remove existing job with same ID if re-scheduling
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

        scheduler.add_job(
            func=dispatch_reminder,
            trigger=CronTrigger(
                day_of_week=cron_days,
                hour=hour,
                minute=minute,
                timezone=pytz.timezone(SCHEDULER_TIMEZONE),
            ),
            args=[reminder_doc, time_label],
            id=job_id,
            name=f"{reminder_doc.get('medicine_name')} @ {time_label}",
            replace_existing=True,
            misfire_grace_time=300,   # 5-minute grace window
        )
        logger.info("Scheduled job %s for reminder %s", job_id, reminder_id)


def remove_reminder_jobs(reminder_id: str, slot_count: int = 10):
    """Remove all APScheduler jobs for a given reminder_id."""
    scheduler = get_scheduler()
    for i in range(slot_count):
        job_id = f"reminder_{reminder_id}_{i}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info("Removed job %s", job_id)


# ── Routes ────────────────────────────────────────────────────────────────────

@reminders_bp.route("", methods=["POST"])
@token_required
def create_reminder():
    """
    Create a new medicine reminder and schedule it.

    Expected JSON body:
    {
        "medicine_name": "Metformin",
        "dosage_note": "1 tablet after breakfast",
        "times": [
            {"id": "morning", "label": "Morning", "time": "08:00"},
            {"id": "night",   "label": "Night",   "time": "21:00"}
        ],
        "frequency": "daily",                          // "daily" | "weekly" | "custom"
        "days_of_week": ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
        "notify_via": "both",                          // "email" | "whatsapp" | "both"
        "contact_email": "patient@example.com",
        "contact_whatsapp": "+919876543210",
        "start_date": "2025-01-01",
        "end_date": "2025-01-31",
        "active": true
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400

        # Validate required fields
        medicine_name = (data.get("medicine_name") or "").strip()
        if not medicine_name:
            return jsonify({"error": "medicine_name is required"}), 400

        notify_via = data.get("notify_via", "email")
        if notify_via not in ("email", "whatsapp", "both"):
            return jsonify({"error": "notify_via must be 'email', 'whatsapp', or 'both'"}), 400

        if notify_via in ("email", "both") and not data.get("contact_email"):
            return jsonify({"error": "contact_email is required for email notifications"}), 400
        if notify_via in ("whatsapp", "both") and not data.get("contact_whatsapp"):
            return jsonify({"error": "contact_whatsapp is required for WhatsApp notifications"}), 400

        times = data.get("times", [])
        if not times:
            return jsonify({"error": "At least one reminder time is required"}), 400

        # Build reminder document
        reminder_doc = {
            "user_id":          request.user_id,
            "medicine_name":    medicine_name,
            "dosage_note":      (data.get("dosage_note") or "").strip(),
            "times":            times,
            "frequency":        data.get("frequency", "daily"),
            "days_of_week":     data.get("days_of_week", ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]),
            "notify_via":       notify_via,
            "contact_email":    (data.get("contact_email") or "").strip(),
            "contact_whatsapp": (data.get("contact_whatsapp") or "").strip(),
            "start_date":       data.get("start_date", date.today().isoformat()),
            "end_date":         data.get("end_date", ""),
            "active":           data.get("active", True),
            "created_at":       datetime.utcnow().isoformat(),
            "notify_via": data.get("notify_via") or data.get("notifyVia"),
            "contact_whatsapp": data.get("contact_whatsapp") or data.get("phone"),
        }

        # Persist to database
        db = get_db()
        result = db.reminders.insert_one(reminder_doc)
        reminder_id = str(result.inserted_id)
        reminder_doc["_id"] = reminder_id

        # Schedule APScheduler jobs
        if reminder_doc["active"]:
            schedule_reminder_jobs(reminder_id, reminder_doc)

        # Return created reminder (MongoDB ObjectId → string)
        reminder_doc.pop("_id", None)
        return jsonify({"id": reminder_id, **reminder_doc}), 201
    


    except Exception as e:
        logger.exception("Error creating reminder")
        return jsonify({"error": "Failed to create reminder"}), 500


@reminders_bp.route("", methods=["GET"])
@token_required
def list_reminders():
    """
    List all reminders for the authenticated user.
    """
    try:
        db = get_db()
        docs = list(db.reminders.find({"user_id": request.user_id}))
        reminders = []
        for doc in docs:
            doc["id"] = str(doc.pop("_id"))
            reminders.append(doc)
        return jsonify({"reminders": reminders, "count": len(reminders)}), 200
    except Exception as e:
        logger.exception("Error listing reminders")
        return jsonify({"error": "Failed to fetch reminders"}), 500


@reminders_bp.route("/<reminder_id>", methods=["GET"])
@token_required
def get_reminder(reminder_id: str):
    """Get a single reminder by ID."""
    try:
        from bson import ObjectId
        db = get_db()
        doc = db.reminders.find_one({"_id": ObjectId(reminder_id), "user_id": request.user_id})
        if not doc:
            return jsonify({"error": "Reminder not found"}), 404
        doc["id"] = str(doc.pop("_id"))
        return jsonify(doc), 200
    except Exception as e:
        logger.exception("Error fetching reminder")
        return jsonify({"error": "Failed to fetch reminder"}), 500


@reminders_bp.route("/<reminder_id>", methods=["PUT"])
@token_required
def update_reminder(reminder_id: str):
    """
    Update a reminder (e.g. change times, pause/resume, change contact).
    Re-schedules APScheduler jobs accordingly.
    """
    try:
        from bson import ObjectId
        db = get_db()

        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400

        # Fetch existing
        doc = db.reminders.find_one({"_id": ObjectId(reminder_id), "user_id": request.user_id})
        if not doc:
            return jsonify({"error": "Reminder not found or unauthorized"}), 404

        # Fields allowed to be updated
        updatable = [
            "medicine_name", "dosage_note", "times", "frequency", "days_of_week",
            "notify_via", "contact_email", "contact_whatsapp", "start_date", "end_date", "active",
        ]
        updates = {k: data[k] for k in updatable if k in data}
        updates["updated_at"] = datetime.utcnow().isoformat()

        db.reminders.update_one({"_id": ObjectId(reminder_id)}, {"$set": updates})

        # Rebuild local doc for re-scheduling
        updated_doc = {**doc, **updates}

        # Remove old jobs
        old_slot_count = len(doc.get("times", []))
        remove_reminder_jobs(reminder_id, slot_count=old_slot_count + 5)

        # Re-schedule if still active
        if updated_doc.get("active", True):
            schedule_reminder_jobs(reminder_id, updated_doc)

        updated_doc["id"] = reminder_id
        updated_doc.pop("_id", None)
        return jsonify(updated_doc), 200

    except Exception as e:
        logger.exception("Error updating reminder")
        return jsonify({"error": "Failed to update reminder"}), 500


@reminders_bp.route("/<reminder_id>", methods=["DELETE"])
@token_required
def delete_reminder(reminder_id: str):
    """Delete a reminder and remove its scheduled jobs."""
    try:
        from bson import ObjectId
        db = get_db()

        doc = db.reminders.find_one({"_id": ObjectId(reminder_id), "user_id": request.user_id})
        if not doc:
            return jsonify({"error": "Reminder not found or unauthorized"}), 404

        # Remove APScheduler jobs first
        remove_reminder_jobs(reminder_id, slot_count=len(doc.get("times", [])) + 5)

        # Delete from DB
        db.reminders.delete_one({"_id": ObjectId(reminder_id)})

        return jsonify({"message": "Reminder deleted successfully"}), 200

    except Exception as e:
        logger.exception("Error deleting reminder")
        return jsonify({"error": "Failed to delete reminder"}), 500


@reminders_bp.route("/<reminder_id>/toggle", methods=["POST"])
@token_required
def toggle_reminder(reminder_id: str):
    """Pause or resume a reminder without deleting it."""
    try:
        from bson import ObjectId
        db = get_db()

        doc = db.reminders.find_one({"_id": ObjectId(reminder_id), "user_id": request.user_id})
        if not doc:
            return jsonify({"error": "Reminder not found or unauthorized"}), 404

        new_active = not doc.get("active", True)
        db.reminders.update_one(
            {"_id": ObjectId(reminder_id)},
            {"$set": {"active": new_active, "updated_at": datetime.utcnow().isoformat()}},
        )

        if new_active:
            schedule_reminder_jobs(reminder_id, {**doc, "active": True})
        else:
            remove_reminder_jobs(reminder_id, slot_count=len(doc.get("times", [])) + 5)

        return jsonify({"id": reminder_id, "active": new_active}), 200

    except Exception as e:
        logger.exception("Error toggling reminder")
        return jsonify({"error": "Failed to toggle reminder"}), 500


@reminders_bp.route("/<reminder_id>/test", methods=["POST"])
@token_required
def test_reminder(reminder_id: str):
    """
    Send a test notification immediately so the user can verify their contact details.
    """
    try:
        from bson import ObjectId
        db = get_db()

        doc = db.reminders.find_one({"_id": ObjectId(reminder_id), "user_id": request.user_id})
        if not doc:
            return jsonify({"error": "Reminder not found or unauthorized"}), 404

        dispatch_reminder(doc, time_label="Test Notification")
        return jsonify({"message": "Test notification sent"}), 200

    except Exception as e:
        logger.exception("Error sending test notification")
        return jsonify({"error": "Failed to send test notification"}), 500


@reminders_bp.route("/health", methods=["GET"])
def health():
    scheduler = get_scheduler()
    return jsonify({
        "status": "ok",
        "service": "reminders",
        "scheduler_running": scheduler.running,
        "job_count": len(scheduler.get_jobs()),
    }), 200


# ── App factory integration ───────────────────────────────────────────────────
# In your main app.py / create_app(), register this blueprint and start the scheduler:
#
#   from reminders import reminders_bp, get_scheduler
#
#   app.register_blueprint(reminders_bp)
#
#   with app.app_context():
#       get_scheduler()   # starts the scheduler on app boot