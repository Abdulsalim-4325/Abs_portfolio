import logging
import smtplib
from email.message import EmailMessage
import httpx
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

from app.core.celery_app import celery_app
from app.core.config import settings
from app.models.feedback import FeedbackEntry

logger = logging.getLogger("abscode.tasks")

sync_engine = create_engine(settings.sync_database_url, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(bind=sync_engine)


def is_smtp_configured() -> bool:
    pwd = (settings.SMTP_PASSWORD or "").strip()
    usr = (settings.SMTP_USER or "").strip()
    return bool(
        usr
        and pwd
        and "your_email" not in usr
        and "your_16" not in pwd
        and "your16" not in pwd
    )


def execute_smtp_otp(recipient: str, otp_code: str) -> bool:
    print(f"\n==========================================", flush=True)
    print(f"[ABSCODE OTP] Recipient: {recipient} | OTP: {otp_code}", flush=True)
    print(f"==========================================\n", flush=True)

    if not is_smtp_configured():
        logger.warning(f"SMTP password not set in .env; logged OTP for {recipient} to container stdout.")
        return False

    msg = EmailMessage()
    msg["Subject"] = f"{otp_code} is your ABSCODE Portfolio verification code"
    msg["From"] = f"ABSCODE Portfolio <{settings.SMTP_USER}>"
    msg["To"] = recipient

    msg.set_content(
        f"Hello,\n\n"
        f"Your 6-digit verification code for Abdul Salim's (ABSCODE) portfolio is:\n\n"
        f"    {otp_code}\n\n"
        f"This code expires in 10 minutes. Do not share it with anyone.\n"
    )

    msg.add_alternative(
        f"""
        <div style="background:#050507;color:#ffffff;font-family:Arial,sans-serif;padding:28px;border-radius:12px;border:1px solid #ff1e2e;max-width:460px;">
          <h2 style="color:#ff1e2e;margin:0 0 12px 0;letter-spacing:1px;">ABSCODE VERIFICATION</h2>
          <p style="color:#cccccc;font-size:14px;line-height:1.5;">Use the 6-digit one-time passcode below to verify your identity and unlock feedback submission:</p>
          <div style="background:#101016;border:1px solid #ff1e2e;border-radius:8px;padding:16px;text-align:center;font-size:28px;font-weight:bold;letter-spacing:8px;color:#ffffff;margin:18px 0;">
            {otp_code}
          </div>
          <p style="color:#888899;font-size:12px;margin:0;">Valid for 10 minutes. If you did not request this code, ignore this email.</p>
        </div>
        """,
        subtype="html",
    )

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD.replace(" ", ""))
        server.send_message(msg)

    logger.info(f"OTP email delivered to {recipient}")
    return True


def execute_drive_sheet_action(payload: dict) -> bool:
    if not settings.GOOGLE_SHEET_WEBHOOK_URL:
        logger.warning("GOOGLE_SHEET_WEBHOOK_URL is not configured. Skipping Drive sync.")
        return False

    with httpx.Client(follow_redirects=True, timeout=20.0) as client:
        response = client.post(settings.GOOGLE_SHEET_WEBHOOK_URL, json=payload)
        response.raise_for_status()

    if payload.get("action", "append") == "append" and payload.get("id"):
        with SyncSessionLocal() as db:
            db.execute(
                update(FeedbackEntry)
                .where(FeedbackEntry.id == payload["id"])
                .values(synced_to_drive=True)
            )
            db.commit()

    logger.info(f"Drive webhook action '{payload.get('action', 'append')}' completed for {payload.get('id')}.")
    return True


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def celery_send_otp_task(self, recipient: str, otp_code: str):
    try:
        return execute_smtp_otp(recipient, otp_code)
    except Exception as exc:
        logger.error(f"SMTP OTP delivery failed for {recipient}: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=5, default_retry_delay=20)
def celery_sync_drive_task(self, payload: dict):
    try:
        return execute_drive_sheet_action(payload)
    except Exception as exc:
        logger.error(f"Drive sync failed, retrying: {exc}")
        raise self.retry(exc=exc)
