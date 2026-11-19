import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
import jwt
from fastapi import Depends, HTTPException, Header, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.admin import AdminUser

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_admin_access_token(
    username: str, expires_delta: Optional[timedelta] = None
) -> str:
    """Creates a signed JWT access token for admin user authentication."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": username.lower().strip(),
        "role": "admin",
        "iat": datetime.now(timezone.utc),
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def verify_admin_token(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    db: AsyncSession = Depends(get_db),
) -> AdminUser:
    """
    FastAPI dependency that enforces valid admin JWT tokens.
    Accepts standard 'Authorization: Bearer <token>' or 'X-Admin-Token: <token>'.
    """
    token = None
    if auth and auth.credentials:
        token = auth.credentials
    elif x_admin_token:
        token = x_admin_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing admin authentication token. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        username = payload.get("sub")
        role = payload.get("role")
        if not username or role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Admin privileges required.",
            )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin session expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify user actually exists in the database
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == username.lower().strip())
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin user account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def hash_ip(ip_address: str) -> str:
    """Returns SHA-256 anonymized hash of client IP."""
    clean_ip = (ip_address or "unknown").strip().lower()
    return hashlib.sha256(clean_ip.encode("utf-8")).hexdigest()


def extract_client_ip(request: Request) -> str:
    """Extracts true client IP respecting reverse proxies (nginx, Cloudflare, etc.)."""
    cf_connecting = request.headers.get("cf-connecting-ip")
    if cf_connecting:
        return cf_connecting.strip()

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    return request.client.host if request.client else "unknown"
