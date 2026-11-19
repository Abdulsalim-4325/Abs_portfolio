import asyncio
import csv
import io
import secrets
from typing import Optional, List, Dict
from datetime import datetime, timedelta, timezone
import httpx
import jwt
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Header, Request, BackgroundTasks, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.feedback import FeedbackEntry, PortfolioStats
from app.schemas.feedback import (
    OTPRequestSchema,
    OTPVerifySchema,
    FeedbackCreate,
    FeedbackUpdate,
    FeedbackResponse,
    PortfolioStatsSchema,
    split_person_and_company,
)
from app.services.tasks import (
    celery_sync_drive_task,
    execute_smtp_otp,
    execute_drive_sheet_action,
)

router = APIRouter(prefix="/api/v1", tags=["Portfolio, Auth & Verified Feedback"])

redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
_memory_otp_fallback = {}


def create_verification_token(identifier: str, provider: str) -> str:
    payload = {
        "sub": identifier.lower().strip(),
        "provider": provider.upper(),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=2),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def verify_account_token(token: str, expected_identifier: str) -> str:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        if payload.get("sub") != expected_identifier.lower().strip():
            raise HTTPException(status_code=403, detail="Verification token does not match account ID.")
        return payload.get("provider", "EMAIL-OTP")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Verification session expired. Please verify again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid verification token. Please verify first.")


def require_owner_access(
    x_owner_token: str = Header(..., description="JWT returned after verifying owner email via OTP"),
    x_admin_key: str = Header(..., description="Master Admin Key / DB Secret"),
):
    if x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized: Invalid admin key.")
    try:
        payload = jwt.decode(x_owner_token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        if payload.get("sub") != settings.OWNER_EMAIL.lower().strip():
            raise HTTPException(status_code=403, detail="Unauthorized: Only the verified owner email can access logs.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired owner verification token.")


async def _issue_and_deliver_otp(email_lower: str) -> None:
    otp_code = f"{secrets.randbelow(900000) + 100000}"
    try:
        await redis_client.setex(f"otp:{email_lower}", 600, otp_code)
        await redis_client.delete(f"otp_attempts:{email_lower}")
    except Exception:
        _memory_otp_fallback[email_lower] = {"code": otp_code, "attempts": 0}

    try:
        await asyncio.to_thread(execute_smtp_otp, email_lower, otp_code)
    except Exception as exc:
        # Still keep OTP in Redis and container logs so user isn't blocked if Gmail blocks port 587
        print(f"[SMTP WARNING] Could not send via Gmail ({exc}). Use OTP from logs: {otp_code}", flush=True)


async def _verify_otp_code(email_lower: str, submitted_code: str) -> None:
    if not submitted_code.isdigit() or len(submitted_code) != 6:
        raise HTTPException(status_code=400, detail="OTP must be an exact 6-digit numeric code.")

    try:
        stored_otp = await redis_client.get(f"otp:{email_lower}")
        if not stored_otp:
            raise HTTPException(status_code=400, detail="No active OTP found or OTP expired. Request a new code.")

        attempts = await redis_client.incr(f"otp_attempts:{email_lower}")
        await redis_client.expire(f"otp_attempts:{email_lower}", 600)

        if attempts > 5:
            await redis_client.delete(f"otp:{email_lower}", f"otp_attempts:{email_lower}")
            raise HTTPException(status_code=429, detail="Too many wrong OTP attempts. Code invalidated.")

        if not secrets.compare_digest(stored_otp, submitted_code):
            remaining = max(0, 5 - attempts)
            raise HTTPException(status_code=400, detail=f"Incorrect OTP code. {remaining} attempts remaining.")

        await redis_client.delete(f"otp:{email_lower}", f"otp_attempts:{email_lower}")
    except HTTPException:
        raise
    except Exception:
        record = _memory_otp_fallback.get(email_lower)
        if not record:
            raise HTTPException(status_code=400, detail="No active OTP found. Request a new OTP.")
        record["attempts"] += 1
        if record["attempts"] > 5:
            _memory_otp_fallback.pop(email_lower, None)
            raise HTTPException(status_code=429, detail="Too many wrong attempts. Request a new OTP.")
        if not secrets.compare_digest(record["code"], submitted_code):
            raise HTTPException(status_code=400, detail="Incorrect OTP code.")
        _memory_otp_fallback.pop(email_lower, None)


@router.post("/auth/send-otp")
async def send_verification_otp(payload: OTPRequestSchema):
    email_lower = payload.email.lower().strip()
    await _issue_and_deliver_otp(email_lower)
    return {"message": f"6-digit verification code sent to {email_lower}. Please check your inbox."}


@router.post("/auth/verify-otp")
async def confirm_verification_otp(payload: OTPVerifySchema):
    email_lower = payload.email.lower().strip()
    await _verify_otp_code(email_lower, payload.otp_code.strip())
    provider = (payload.provider or "EMAIL-OTP").upper().strip()
    identifier = (payload.identifier or email_lower).strip()
    token = create_verification_token(identifier, provider)
    return {"email": identifier, "verification_token": token, "provider": provider}


def _oauth_popup_close_html(identifier: str, token: str, provider: str) -> HTMLResponse:
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html><body style="background:#050507;color:#fff;font-family:sans-serif;text-align:center;padding-top:40px;">
      <h3 style="color:#27e878;">✓ Verified {identifier} ({provider})</h3>
      <p>Returning to ABSCODE Portfolio...</p>
      <script>
        if (window.opener) {{
          window.opener.postMessage({{
            type: 'OAUTH_VERIFIED',
            email: '{identifier}',
            verification_token: '{token}',
            provider: '{provider}'
          }}, '*');
        }}
        setTimeout(() => window.close(), 300);
      </script>
    </body></html>
    """)


@router.get("/auth/oauth/{provider}/direct-oauth")
async def direct_oauth_provider(provider: str):
    clean_p = provider.lower().replace("-2fa", "")
    if clean_p == "google" and settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
        redirect_uri = f"{settings.OAUTH_REDIRECT_BASE}/google/callback"
        return RedirectResponse(
            f"https://accounts.google.com/o/oauth2/v2/auth?client_id={settings.GOOGLE_CLIENT_ID}"
            f"&response_type=code&scope=openid%20email%20profile&redirect_uri={redirect_uri}&prompt=select_account"
        )
    if clean_p == "github" and settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_SECRET:
        redirect_uri = f"{settings.OAUTH_REDIRECT_BASE}/github/callback"
        return RedirectResponse(
            f"https://github.com/login/oauth/authorize?client_id={settings.GITHUB_CLIENT_ID}"
            f"&scope=read:user%20user:email&redirect_uri={redirect_uri}"
        )
    return RedirectResponse(f"/api/v1/auth/oauth/{clean_p}")


@router.get("/auth/oauth/{provider}")
async def oauth_login_redirect(provider: str, hint: str = ""):
    clean_p = provider.lower().replace("-2fa", "")
    provider_upper = clean_p.upper()

    has_oauth_direct = (
        (clean_p == "google" and bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET))
        or (clean_p == "github" and bool(settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_SECRET))
    )

    oauth_btn_html = ""
    if has_oauth_direct:
        provider_display = "Google Account" if clean_p == "google" else "GitHub Account"
        oauth_btn_html = f"""
        <div style="margin-bottom:18px;">
          <a href="/api/v1/auth/oauth/{clean_p}/direct-oauth" class="oauth-quick-btn">
            Sign In with {provider_display} (1-Click) &rarr;
          </a>
          <div class="or-divider"><span>OR VERIFY VIA 2-FACTOR CODE</span></div>
        </div>
        """

    # Field configurations
    if clean_p == "google":
        form_fields_html = f"""
          <label>Google / Gmail Address</label>
          <input type="email" name="email" value="{hint if '@' in hint else ''}" placeholder="your.name@gmail.com" required autofocus />
          <input type="hidden" name="identifier" value="" />
        """
        desc_text = "Enter your Google / Gmail address to receive your 6-digit verification code:"
    elif clean_p == "github":
        form_fields_html = f"""
          <label>GitHub Username (@handle)</label>
          <input type="text" name="identifier" value="{hint if not '@' in hint else ''}" placeholder="e.g. AbdulSalim-4325" required autofocus />
          <label>Email Address (to receive 6-digit OTP)</label>
          <input type="email" name="email" value="{hint if '@' in hint else ''}" placeholder="your_email@gmail.com" required />
        """
        desc_text = "Enter your GitHub account details to receive your 6-digit verification code:"
    else:  # Instagram
        form_fields_html = f"""
          <label>Instagram Handle (@username)</label>
          <input type="text" name="identifier" value="{hint if not '@' in hint or hint.startswith('@') else ''}" placeholder="e.g. @_absalim__" required autofocus />
          <label>Email Address (to receive 6-digit OTP)</label>
          <input type="email" name="email" value="{hint if '@' in hint and not hint.startswith('@') else ''}" placeholder="your_email@gmail.com" required />
        """
        desc_text = "Enter your Instagram handle and email to receive your 6-digit verification code:"

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>{provider_upper} 2-Factor Authentication</title>
      <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
          background: #050507;
          color: #ffffff;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 100vh;
          padding: 16px;
        }}
        .auth-card {{
          background: #101016;
          border: 1px solid #ff1e2e;
          border-radius: 16px;
          padding: 28px 22px;
          width: 100%;
          max-width: 390px;
          text-align: center;
          box-shadow: 0 0 35px rgba(255, 30, 46, 0.3);
        }}
        .brand-hdr {{
          font-size: 0.82rem;
          font-weight: 800;
          letter-spacing: 2.5px;
          color: #ffffff;
          margin-bottom: 6px;
        }}
        .brand-hdr span {{ color: #ff1e2e; }}
        h2 {{
          font-size: 1.12rem;
          color: #ff1e2e;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          margin-bottom: 10px;
        }}
        p.subtitle {{
          font-size: 0.8rem;
          color: #b8b8c4;
          line-height: 1.45;
          margin-bottom: 18px;
        }}
        .oauth-quick-btn {{
          display: block;
          width: 100%;
          padding: 11px;
          background: rgba(255, 30, 46, 0.12);
          border: 1px solid #ff1e2e;
          color: #ffffff;
          text-decoration: none;
          border-radius: 8px;
          font-size: 0.82rem;
          font-weight: 700;
          letter-spacing: 0.5px;
          transition: background 0.2s;
        }}
        .oauth-quick-btn:hover {{
          background: #ff1e2e;
        }}
        .or-divider {{
          display: flex;
          align-items: center;
          text-align: center;
          margin: 14px 0 6px 0;
        }}
        .or-divider::before, .or-divider::after {{
          content: '';
          flex: 1;
          border-bottom: 1px solid #2b2b36;
        }}
        .or-divider span {{
          padding: 0 10px;
          font-size: 0.68rem;
          color: #7b7b8c;
          letter-spacing: 1px;
        }}
        label {{
          display: block;
          text-align: left;
          font-size: 0.74rem;
          font-weight: 600;
          color: #a6a6b2;
          margin: 10px 0 4px 2px;
          letter-spacing: 0.5px;
        }}
        input {{
          width: 100%;
          padding: 11px 12px;
          border-radius: 8px;
          border: 1px solid #2b2b36;
          background: #050507;
          color: #ffffff;
          margin-bottom: 6px;
          font-size: 0.9rem;
          outline: none;
          transition: border-color 0.2s;
        }}
        input:focus {{ border-color: #ff1e2e; }}
        button.btn-submit {{
          width: 100%;
          padding: 13px;
          background: #ff1e2e;
          color: #ffffff;
          border: none;
          border-radius: 8px;
          font-weight: 700;
          font-size: 0.88rem;
          letter-spacing: 0.6px;
          cursor: pointer;
          margin-top: 10px;
          transition: background 0.2s;
        }}
        button.btn-submit:hover {{ background: #d91424; }}
      </style>
    </head>
    <body>
      <div class="auth-card">
        <div class="brand-hdr">ABS<span>CODE</span> // AUTHENTICATOR</div>
        <h2>{provider_upper} 2FA VERIFICATION</h2>
        <p class="subtitle">{desc_text}</p>
        {oauth_btn_html}
        <form action="/api/v1/auth/oauth/{clean_p}/send-code" method="post">
          {form_fields_html}
          <button type="submit" class="btn-submit">SEND 6-DIGIT VERIFICATION CODE</button>
        </form>
      </div>
    </body>
    </html>
    """)


@router.post("/auth/oauth/{provider}/send-code")
async def oauth_popup_send_code(
    provider: str,
    email: str = Form(...),
    identifier: Optional[str] = Form(None),
):
    email_lower = email.lower().strip()
    clean_p = provider.lower().replace("-2fa", "")
    provider_upper = clean_p.upper()

    clean_id = (identifier or "").strip()
    if not clean_id:
        clean_id = email_lower
    elif clean_p == "instagram" and not clean_id.startswith("@"):
        clean_id = f"@{clean_id}"

    await _issue_and_deliver_otp(email_lower)

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Confirm {provider_upper} Passcode</title>
      <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
          background: #050507;
          color: #ffffff;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 100vh;
          padding: 16px;
        }}
        .auth-card {{
          background: #101016;
          border: 1px solid #ff1e2e;
          border-radius: 16px;
          padding: 28px 22px;
          width: 100%;
          max-width: 390px;
          text-align: center;
          box-shadow: 0 0 35px rgba(255, 30, 46, 0.3);
        }}
        .brand-hdr {{
          font-size: 0.82rem;
          font-weight: 800;
          letter-spacing: 2.5px;
          color: #ffffff;
          margin-bottom: 6px;
        }}
        .brand-hdr span {{ color: #ff1e2e; }}
        h2 {{
          font-size: 1.15rem;
          color: #ff1e2e;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          margin-bottom: 10px;
        }}
        p.subtitle {{
          font-size: 0.82rem;
          color: #b8b8c4;
          line-height: 1.45;
          margin-bottom: 18px;
        }}
        p.subtitle strong {{ color: #27e878; }}
        input.code-input {{
          width: 100%;
          padding: 13px;
          border-radius: 8px;
          border: 1px solid #2b2b36;
          background: #050507;
          color: #ffffff;
          font-size: 1.3rem;
          font-weight: 800;
          text-align: center;
          letter-spacing: 8px;
          outline: none;
          transition: border-color 0.2s;
          margin-bottom: 14px;
        }}
        input.code-input:focus {{ border-color: #27e878; }}
        button.btn-verify {{
          width: 100%;
          padding: 13px;
          background: #27e878;
          color: #050507;
          border: none;
          border-radius: 8px;
          font-weight: 800;
          font-size: 0.9rem;
          letter-spacing: 0.8px;
          cursor: pointer;
          transition: background 0.2s;
        }}
        button.btn-verify:hover {{ background: #22cb69; }}
        .resend-row {{
          margin-top: 14px;
          font-size: 0.75rem;
          color: #7b7b8c;
        }}
        .resend-row a {{
          color: #ff1e2e;
          text-decoration: underline;
        }}
      </style>
    </head>
    <body>
      <div class="auth-card">
        <div class="brand-hdr">ABS<span>CODE</span> // AUTHENTICATOR</div>
        <h2>ENTER 6-DIGIT CODE</h2>
        <p class="subtitle">Code sent to <strong>{email_lower}</strong> to verify <strong>{clean_id}</strong> ({provider_upper}):</p>
        <form action="/api/v1/auth/oauth/{clean_p}/confirm-code" method="post">
          <input type="hidden" name="identifier" value="{clean_id}" />
          <input type="hidden" name="email" value="{email_lower}" />
          <input type="text" name="otp_code" class="code-input" maxlength="6" placeholder="000000" required autofocus />
          <button type="submit" class="btn-verify">VERIFY &amp; UNLOCK</button>
        </form>
        <div class="resend-row">
          Didn't receive code? <a href="/api/v1/auth/oauth/{clean_p}?hint={clean_id}">Request new code</a>
        </div>
      </div>
    </body>
    </html>
    """)


@router.post("/auth/oauth/{provider}/confirm-code")
async def oauth_popup_confirm_code(
    provider: str,
    email: str = Form(...),
    otp_code: str = Form(...),
    identifier: Optional[str] = Form(None),
):
    email_lower = email.lower().strip()
    clean_p = provider.lower().replace("-2fa", "")
    provider_upper = clean_p.upper()

    clean_id = (identifier or "").strip()
    if not clean_id:
        clean_id = email_lower
    elif clean_p == "instagram" and not clean_id.startswith("@"):
        clean_id = f"@{clean_id}"

    try:
        await _verify_otp_code(email_lower, otp_code.strip())
    except HTTPException as exc:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html><head><meta charset="utf-8"><title>Verification Failed</title><style>
          body {{ background:#050507; color:#ff4d5a; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:90vh; text-align:center; }}
          .box {{ background:#101016; border:1px solid #ff1e2e; border-radius:14px; padding:26px; max-width:380px; box-shadow:0 0 30px rgba(255,30,46,0.3); }}
          h3 {{ margin-bottom:10px; color:#ff1e2e; }}
          p {{ color:#b8b8c4; font-size:0.85rem; margin-bottom:14px; }}
          a.btn {{ display:inline-block; padding:11px 18px; background:#ff1e2e; color:#fff; text-decoration:none; border-radius:8px; font-weight:700; font-size:0.85rem; }}
        </style></head>
        <body>
          <div class="box">
            <h3>Verification Failed</h3>
            <p>{exc.detail}</p>
            <a class="btn" href="/api/v1/auth/oauth/{clean_p}?hint={clean_id}">TRY AGAIN &rarr;</a>
          </div>
        </body></html>
        """, status_code=400)

    jwt_token = create_verification_token(clean_id, provider_upper)
    return _oauth_popup_close_html(clean_id, jwt_token, provider_upper)


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_verified_feedback(
    payload: FeedbackCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    provider = verify_account_token(payload.verification_token, payload.verified_identifier)
    person_name, company_name = split_person_and_company(payload.raw_name_or_company)

    email_col = payload.email
    insta_col = payload.insta_id
    google_col = payload.google_account
    github_col = payload.github_account

    ident = payload.verified_identifier.strip()
    if provider == "EMAIL-OTP":
        email_col = email_col or ident
    elif provider == "GOOGLE":
        google_col = google_col or ident
        if "@" in ident:
            email_col = email_col or ident
    elif provider == "GITHUB":
        github_col = github_col or ident
    elif provider == "INSTAGRAM":
        insta_col = insta_col or (ident if ident.startswith("@") else f"@{ident}")

    clamped_rating = min(5, max(1, payload.rating))
    visual_stars = ("★" * clamped_rating) + ("☆" * (5 - clamped_rating))

    words = [w for w in payload.message.strip().split() if w]
    word_count = len(words)

    forwarded_for = request.headers.get("x-forwarded-for")
    client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else (
        request.client.host if request.client else "unknown"
    )
    user_agent = request.headers.get("user-agent", "unknown")[:512]

    entry = FeedbackEntry(
        person_name=person_name,
        company_name=company_name,
        email=email_col,
        insta_id=insta_col,
        google_account=google_col,
        github_account=github_col,
        verification_provider=provider,
        rating=clamped_rating,
        rating_stars=visual_stars,
        word_count=word_count,
        message=payload.message.strip(),
        client_ip=client_ip,
        user_agent=user_agent,
    )

    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    sync_payload = {
        "action": "append",
        "id": entry.id,
        "created_at": entry.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "person_name": entry.person_name,
        "company_name": entry.company_name,
        "email": entry.email,
        "insta_id": entry.insta_id,
        "google_account": entry.google_account,
        "github_account": entry.github_account,
        "verification_provider": entry.verification_provider,
        "rating": entry.rating,
        "rating_stars": entry.rating_stars,
        "word_count": entry.word_count,
        "message": entry.message,
        "client_ip": entry.client_ip,
        "user_agent": entry.user_agent,
    }

    # Ensure data is saved to Google Sheet Excel immediately in background
    background_tasks.add_task(asyncio.to_thread, execute_drive_sheet_action, sync_payload)
    try:
        celery_sync_drive_task.delay(sync_payload)
    except Exception:
        pass

    return entry


@router.get("/feedback/manage", response_model=list[FeedbackResponse], dependencies=[Depends(require_owner_access)])
async def list_all_feedback_owner_only(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FeedbackEntry).order_by(FeedbackEntry.created_at.desc()))
    return result.scalars().all()


@router.patch("/feedback/manage/{feedback_id}", response_model=FeedbackResponse, dependencies=[Depends(require_owner_access)])
async def update_feedback_owner_only(
    feedback_id: str,
    payload: FeedbackUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(FeedbackEntry, feedback_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Feedback record not found.")

    if payload.person_name is not None:
        entry.person_name = payload.person_name
    if payload.company_name is not None:
        entry.company_name = payload.company_name
    if payload.rating is not None:
        entry.rating = payload.rating
        entry.rating_stars = ("★" * payload.rating) + ("☆" * (5 - payload.rating))
    if payload.message is not None:
        entry.message = payload.message.strip()
        entry.word_count = len([w for w in entry.message.split() if w])

    await db.commit()
    await db.refresh(entry)

    sync_payload = {
        "action": "update",
        "id": entry.id,
        "person_name": entry.person_name,
        "company_name": entry.company_name,
        "rating": entry.rating,
        "rating_stars": entry.rating_stars,
        "word_count": entry.word_count,
        "message": entry.message,
    }
    # Ensure data is saved to Google Sheet Excel immediately in background
    background_tasks.add_task(asyncio.to_thread, execute_drive_sheet_action, sync_payload)
    try:
        celery_sync_drive_task.delay(sync_payload)
    except Exception:
        pass

    return entry


@router.delete("/feedback/manage/{feedback_id}", dependencies=[Depends(require_owner_access)])
async def delete_feedback_owner_only(
    feedback_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(FeedbackEntry, feedback_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Feedback record not found.")

    await db.delete(entry)
    await db.commit()

    sync_payload = {"action": "delete", "id": feedback_id}
    try:
        celery_sync_drive_task.delay(sync_payload)
    except Exception:
        background_tasks.add_task(asyncio.to_thread, execute_drive_sheet_action, sync_payload)

    return {"status": "deleted", "id": feedback_id, "synced_to_drive": True}


@router.get("/feedback/export-excel-csv", dependencies=[Depends(require_owner_access)])
async def export_all_feedback_csv(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FeedbackEntry).order_by(FeedbackEntry.created_at.desc()))
    rows = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Feedback_ID", "Date_And_Time_UTC", "Person_Name", "Company_Name",
        "Email", "Insta_ID", "Google_Account", "GitHub_Account",
        "Verified_Via", "Rating_Number", "Rating_Stars", "Word_Count",
        "Feedback_Message", "Client_IP", "User_Agent", "Synced_To_Drive"
    ])
    for r in rows:
        writer.writerow([
            r.id, r.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            r.person_name or "", r.company_name or "",
            r.email or "", r.insta_id or "", r.google_account or "", r.github_account or "",
            r.verification_provider, r.rating, r.rating_stars, r.word_count,
            r.message, r.client_ip, r.user_agent, r.synced_to_drive
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=abscode_feedback_complete_log.csv"},
    )


@router.get("/portfolio-stats", response_model=PortfolioStatsSchema)
async def get_portfolio_stats(db: AsyncSession = Depends(get_db)):
    stats = await db.get(PortfolioStats, 1)
    if not stats:
        stats = PortfolioStats(id=1, hackathons_count=3, projects_count=6, research_papers_count=1)
        db.add(stats)
        await db.commit()
        await db.refresh(stats)
    return stats


@router.put("/portfolio-stats", response_model=PortfolioStatsSchema)
async def update_portfolio_stats(
    payload: PortfolioStatsSchema,
    x_admin_key: str = Header(..., description="Master Admin API Key from .env"),
    db: AsyncSession = Depends(get_db),
):
    if x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid Admin API Key.")

    stats = await db.get(PortfolioStats, 1)
    if not stats:
        stats = PortfolioStats(id=1)
        db.add(stats)

    stats.hackathons_count = payload.hackathons_count
    stats.projects_count = payload.projects_count
    stats.research_papers_count = payload.research_papers_count
    await db.commit()
    await db.refresh(stats)
    return stats

@router.get("/auth/oauth/google/callback")
async def google_oauth_callback(code: Optional[str] = None, error: Optional[str] = None):
    if error or not code:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html><head><meta charset="utf-8"><title>Google Verification Notice</title><style>
          body {{ background:#050507; color:#fff; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:90vh; text-align:center; }}
          .box {{ background:#101016; border:1px solid #ff1e2e; border-radius:14px; padding:26px; max-width:390px; box-shadow:0 0 30px rgba(255,30,46,0.3); }}
          h3 {{ color:#ff1e2e; margin-bottom:10px; text-transform:uppercase; letter-spacing:1px; }}
          p {{ color:#b8b8c4; font-size:0.85rem; line-height:1.45; margin-bottom:14px; }}
          a.btn {{ display:inline-block; padding:12px 20px; background:#ff1e2e; color:#fff; text-decoration:none; border-radius:8px; font-weight:700; font-size:0.88rem; }}
        </style></head>
        <body>
          <div class="box">
            <h3>Google Authentication</h3>
            <p>{error or 'Google authorization code was not received or request was canceled.'}</p>
            <p>You can verify your Google identity directly using our 2-Factor OTP authenticator:</p>
            <a class="btn" href="/api/v1/auth/oauth/google?fallback=1">USE GOOGLE 2-FACTOR OTP &rarr;</a>
          </div>
        </body></html>
        """)

    redirect_uri = f"{settings.OAUTH_REDIRECT_BASE}/google/callback"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_res = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if token_res.status_code != 200:
                err_detail = "Google token exchange failed"
                try:
                    err_detail = token_res.json().get("error_description", token_res.text[:100])
                except Exception:
                    pass
                return HTMLResponse(f"""
                <!DOCTYPE html>
                <html><head><meta charset="utf-8"><title>Google Verification</title><style>
                  body {{ background:#050507; color:#fff; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:90vh; text-align:center; }}
                  .box {{ background:#101016; border:1px solid #ff1e2e; border-radius:14px; padding:26px; max-width:390px; box-shadow:0 0 30px rgba(255,30,46,0.3); }}
                  h3 {{ color:#ff1e2e; margin-bottom:10px; text-transform:uppercase; letter-spacing:1px; }}
                  p {{ color:#b8b8c4; font-size:0.85rem; line-height:1.45; margin-bottom:14px; }}
                  a.btn {{ display:inline-block; padding:12px 20px; background:#ff1e2e; color:#fff; text-decoration:none; border-radius:8px; font-weight:700; font-size:0.88rem; }}
                </style></head>
                <body>
                  <div class="box">
                    <h3>Google Auth Fallback</h3>
                    <p>{err_detail}</p>
                    <p>Continue verifying your Google identity directly via 2-Factor OTP:</p>
                    <a class="btn" href="/api/v1/auth/oauth/google?fallback=1">CONTINUE WITH 2-FACTOR OTP &rarr;</a>
                  </div>
                </body></html>
                """)

            access_token = token_res.json().get("access_token")
            user_res = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            info = user_res.json()
            verified_email = info.get("email", "").lower().strip()

        if not verified_email:
            raise ValueError("No email returned from Google userinfo")

        jwt_token = create_verification_token(verified_email, "GOOGLE")
        return _oauth_popup_close_html(verified_email, jwt_token, "GOOGLE")
    except Exception as exc:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html><head><meta charset="utf-8"><title>Google Verification Fallback</title><style>
          body {{ background:#050507; color:#fff; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:90vh; text-align:center; }}
          .box {{ background:#101016; border:1px solid #ff1e2e; border-radius:14px; padding:26px; max-width:390px; box-shadow:0 0 30px rgba(255,30,46,0.3); }}
          h3 {{ color:#ff1e2e; margin-bottom:10px; text-transform:uppercase; letter-spacing:1px; }}
          p {{ color:#b8b8c4; font-size:0.85rem; line-height:1.45; margin-bottom:14px; }}
          a.btn {{ display:inline-block; padding:12px 20px; background:#ff1e2e; color:#fff; text-decoration:none; border-radius:8px; font-weight:700; font-size:0.88rem; }}
        </style></head>
        <body>
          <div class="box">
            <h3>Google Auth Fallback</h3>
            <p>{exc}</p>
            <p>Verify your Google account directly via 2-Factor OTP:</p>
            <a class="btn" href="/api/v1/auth/oauth/google?fallback=1">USE GOOGLE 2-FACTOR OTP &rarr;</a>
          </div>
        </body></html>
        """)


@router.get("/auth/oauth/github/callback")
async def github_oauth_callback(code: Optional[str] = None, error: Optional[str] = None):
    if error or not code:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html><head><meta charset="utf-8"><title>GitHub Verification Notice</title><style>
          body {{ background:#050507; color:#fff; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:90vh; text-align:center; }}
          .box {{ background:#101016; border:1px solid #ff1e2e; border-radius:14px; padding:26px; max-width:390px; box-shadow:0 0 30px rgba(255,30,46,0.3); }}
          h3 {{ color:#ff1e2e; margin-bottom:10px; text-transform:uppercase; letter-spacing:1px; }}
          p {{ color:#b8b8c4; font-size:0.85rem; line-height:1.45; margin-bottom:14px; }}
          a.btn {{ display:inline-block; padding:12px 20px; background:#ff1e2e; color:#fff; text-decoration:none; border-radius:8px; font-weight:700; font-size:0.88rem; }}
        </style></head>
        <body>
          <div class="box">
            <h3>GitHub Authentication</h3>
            <p>{error or 'GitHub authorization code was not received or request was canceled.'}</p>
            <p>You can verify your GitHub identity directly using our 2-Factor OTP authenticator:</p>
            <a class="btn" href="/api/v1/auth/oauth/github?fallback=1">USE GITHUB 2-FACTOR OTP &rarr;</a>
          </div>
        </body></html>
        """)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_res = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                },
            )
            if token_res.status_code != 200:
                err_detail = "GitHub token exchange failed"
                try:
                    err_detail = token_res.json().get("error_description", token_res.text[:100])
                except Exception:
                    pass
                return HTMLResponse(f"""
                <!DOCTYPE html>
                <html><head><meta charset="utf-8"><title>GitHub Verification</title><style>
                  body {{ background:#050507; color:#fff; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:90vh; text-align:center; }}
                  .box {{ background:#101016; border:1px solid #ff1e2e; border-radius:14px; padding:26px; max-width:390px; box-shadow:0 0 30px rgba(255,30,46,0.3); }}
                  h3 {{ color:#ff1e2e; margin-bottom:10px; text-transform:uppercase; letter-spacing:1px; }}
                  p {{ color:#b8b8c4; font-size:0.85rem; line-height:1.45; margin-bottom:14px; }}
                  a.btn {{ display:inline-block; padding:12px 20px; background:#ff1e2e; color:#fff; text-decoration:none; border-radius:8px; font-weight:700; font-size:0.88rem; }}
                </style></head>
                <body>
                  <div class="box">
                    <h3>GitHub Auth Fallback</h3>
                    <p>{err_detail}</p>
                    <p>Continue verifying your GitHub identity directly via 2-Factor OTP:</p>
                    <a class="btn" href="/api/v1/auth/oauth/github?fallback=1">CONTINUE WITH 2-FACTOR OTP &rarr;</a>
                  </div>
                </body></html>
                """)

            access_token = token_res.json().get("access_token")
            user_res = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
            )
            gh_login = user_res.json().get("login")

        if not gh_login:
            raise ValueError("No login handle returned from GitHub")

        jwt_token = create_verification_token(gh_login, "GITHUB")
        return _oauth_popup_close_html(gh_login, jwt_token, "GITHUB")
    except Exception as exc:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html><head><meta charset="utf-8"><title>GitHub Verification Fallback</title><style>
          body {{ background:#050507; color:#fff; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:90vh; text-align:center; }}
          .box {{ background:#101016; border:1px solid #ff1e2e; border-radius:14px; padding:26px; max-width:390px; box-shadow:0 0 30px rgba(255,30,46,0.3); }}
          h3 {{ color:#ff1e2e; margin-bottom:10px; text-transform:uppercase; letter-spacing:1px; }}
          p {{ color:#b8b8c4; font-size:0.85rem; line-height:1.45; margin-bottom:14px; }}
          a.btn {{ display:inline-block; padding:12px 20px; background:#ff1e2e; color:#fff; text-decoration:none; border-radius:8px; font-weight:700; font-size:0.88rem; }}
        </style></head>
        <body>
          <div class="box">
            <h3>GitHub Auth Fallback</h3>
            <p>{exc}</p>
            <p>Verify your GitHub account directly via 2-Factor OTP:</p>
            <a class="btn" href="/api/v1/auth/oauth/github?fallback=1">USE GITHUB 2-FACTOR OTP &rarr;</a>
          </div>
        </body></html>
        """)
