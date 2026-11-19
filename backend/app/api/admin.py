import os
import shutil
import uuid
from typing import List, Any
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    UploadFile,
    File,
    status,
)
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    verify_password,
    hash_password,
    create_admin_access_token,
    verify_admin_token,
)
from app.models.admin import AdminUser
from app.models.project import Project
from app.models.site_content import SiteContent
from app.schemas.admin import (
    AdminLoginRequest,
    TokenResponse,
    AdminProfileResponse,
    AdminPasswordChangeRequest,
)
from app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
)
from app.schemas.content import (
    SiteContentItem,
    SiteContentUpdate,
    SiteContentBulkUpdate,
)

admin_router = APIRouter(tags=["Admin & CMS"])


def _resolve_feedback_model():
    """Safely locate the SQLAlchemy feedback model regardless of module/class naming."""
    try:
        from app.models import feedback as feedback_mod
        for attr in ("FeedbackEntry", "Feedback", "FeedbackModel"):
            model = getattr(feedback_mod, attr, None)
            if model is not None and hasattr(model, "__tablename__"):
                return model
    except ImportError:
        pass

    try:
        from app.models import models as models_mod
        for attr in ("FeedbackEntry", "Feedback"):
            model = getattr(models_mod, attr, None)
            if model is not None and hasattr(model, "__tablename__"):
                return model
    except ImportError:
        pass

    return None


# -----------------------------------------------------------------------------
# 1. ADMIN AUTHENTICATION
# -----------------------------------------------------------------------------
@admin_router.post(
    "/admin/login",
    response_model=TokenResponse,
    summary="Admin Login (JWT Issuance)",
)
async def admin_login(
    payload: AdminLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    username_clean = payload.username.lower().strip()
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == username_clean)
    )
    user = result.scalar_one_or_none()

    expected_username = settings.ADMIN_USERNAME.lower().strip()
    expected_password = settings.ADMIN_DEFAULT_PASSWORD

    # Fail-safe authentication for the designated master admin account (salim / Abdul@4325)
    is_master_admin = (
        username_clean == expected_username and payload.password == expected_password
    )

    if is_master_admin:
        if not user:
            user = AdminUser(
                username=expected_username,
                hashed_password=hash_password(expected_password),
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        elif not verify_password(payload.password, user.hashed_password):
            user.hashed_password = hash_password(expected_password)
            await db.commit()
            await db.refresh(user)
    else:
        if not user or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid admin username or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    token = create_admin_access_token(user.username)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        username=user.username,
    )


@admin_router.get(
    "/admin/me",
    response_model=AdminProfileResponse,
    summary="Get Current Authenticated Admin",
)
async def get_admin_profile(
    current_admin: AdminUser = Depends(verify_admin_token),
):
    return AdminProfileResponse(
        id=current_admin.id,
        username=current_admin.username,
        created_at=current_admin.created_at,
    )


@admin_router.post(
    "/admin/change-password",
    summary="Change Admin Password",
)
async def change_admin_password(
    payload: AdminPasswordChangeRequest,
    current_admin: AdminUser = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(payload.current_password, current_admin.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    current_admin.hashed_password = hash_password(payload.new_password)
    await db.commit()
    return {"status": "success", "message": "Admin password updated successfully."}


# -----------------------------------------------------------------------------
# 2. FEEDBACK ENTRIES (ADMIN ONLY)
# -----------------------------------------------------------------------------
@admin_router.get(
    "/admin/feedback",
    summary="List All Feedback Entries",
)
async def list_admin_feedback(
    current_admin: AdminUser = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    model = _resolve_feedback_model()
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Feedback ORM model could not be resolved.",
        )

    order_col = (
        getattr(model, "created_at", None)
        or getattr(model, "timestamp", None)
        or getattr(model, "id", None)
    )
    query = select(model).order_by(desc(order_col)) if order_col is not None else select(model)
    result = await db.execute(query)
    rows: List[Any] = result.scalars().all()

    formatted = []
    for r in rows:
        created_val = getattr(r, "created_at", None) or getattr(r, "timestamp", None)
        rating_val = getattr(r, "rating", getattr(r, "rating_number", 5))
        try:
            rating_int = int(rating_val) if rating_val is not None else 5
        except (ValueError, TypeError):
            rating_int = 5

        stars_val = getattr(r, "rating_stars", None)
        if not stars_val:
            clamped = max(0, min(5, rating_int))
            stars_val = ("★" * clamped) + ("☆" * (5 - clamped))

        formatted.append(
            {
                "id": str(getattr(r, "id", "")),
                "created_at": created_val.isoformat() if hasattr(created_val, "isoformat") else (str(created_val) if created_val else None),
                "person_name": getattr(r, "person_name", None),
                "company_name": getattr(r, "company_name", None),
                "email": getattr(r, "email", None),
                "insta_id": getattr(r, "insta_id", None),
                "google_account": getattr(r, "google_account", None),
                "github_account": getattr(r, "github_account", None),
                "verified_identifier": getattr(r, "verified_identifier", None),
                "verification_provider": getattr(r, "verification_provider", None) or getattr(r, "verified_via", None),
                "rating": rating_int,
                "rating_stars": stars_val,
                "message": getattr(r, "message", None) or getattr(r, "feedback_message", "") or "",
            }
        )

    return formatted


# -----------------------------------------------------------------------------
# 3. CMS PROJECT MUTATIONS (ADMIN ONLY)
# -----------------------------------------------------------------------------
@admin_router.post(
    "/admin/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create New Portfolio Project",
)
async def create_project(
    payload: ProjectCreate,
    current_admin: AdminUser = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    new_project = Project(
        title=payload.title.strip(),
        description=payload.description.strip(),
        image_url=payload.image_url.strip(),
        github_url=(payload.github_url or "").strip(),
        live_url=(payload.live_url or "").strip(),
        tech_stack=payload.tech_stack or [],
        display_order=payload.display_order,
        is_visible=payload.is_visible,
    )
    db.add(new_project)
    await db.commit()
    await db.refresh(new_project)
    return new_project


@admin_router.put(
    "/admin/projects/{project_id}",
    response_model=ProjectResponse,
    summary="Update Existing Portfolio Project",
)
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    current_admin: AdminUser = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    if payload.title is not None:
        project.title = payload.title.strip()
    if payload.description is not None:
        project.description = payload.description.strip()
    if payload.image_url is not None:
        project.image_url = payload.image_url.strip()
    if payload.github_url is not None:
        project.github_url = payload.github_url.strip()
    if payload.live_url is not None:
        project.live_url = payload.live_url.strip()
    if payload.tech_stack is not None:
        project.tech_stack = payload.tech_stack
    if payload.display_order is not None:
        project.display_order = payload.display_order
    if payload.is_visible is not None:
        project.is_visible = payload.is_visible

    await db.commit()
    await db.refresh(project)
    return project


@admin_router.delete(
    "/admin/projects/{project_id}",
    summary="Delete Portfolio Project",
)
async def delete_project(
    project_id: str,
    current_admin: AdminUser = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    await db.delete(project)
    await db.commit()
    return {"status": "deleted", "id": project_id}


@admin_router.post(
    "/admin/projects/upload-image",
    summary="Upload Project Screenshot / Thumbnail",
)
async def upload_project_image(
    request: Request,
    file: UploadFile = File(...),
    current_admin: AdminUser = Depends(verify_admin_token),
):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    allowed_exts = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}
    _, ext = os.path.splitext((file.filename or "").lower())
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image extension ({ext}). Allowed: {', '.join(allowed_exts)}",
        )

    safe_name = f"{uuid.uuid4().hex[:12]}{ext}"
    dest_path = os.path.join(settings.UPLOAD_DIR, safe_name)

    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    base_url = str(request.base_url).rstrip("/")
    rel_url = f"/uploads/{safe_name}"

    return {
        "filename": safe_name,
        "url": rel_url,
        "full_url": f"{base_url}{rel_url}",
    }


# -----------------------------------------------------------------------------
# 4. CMS SITE CONTENT MUTATIONS (ADMIN ONLY)
# -----------------------------------------------------------------------------
@admin_router.get(
    "/admin/site-content",
    response_model=List[SiteContentItem],
    summary="List All Site Content Key-Values",
)
async def list_admin_site_content(
    current_admin: AdminUser = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SiteContent).order_by(SiteContent.key.asc()))
    return result.scalars().all()


@admin_router.put(
    "/admin/site-content/{key}",
    response_model=SiteContentItem,
    summary="Create or Update a Specific Site Content Key",
)
async def upsert_site_content_key(
    key: str,
    payload: SiteContentUpdate,
    current_admin: AdminUser = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    clean_key = key.strip().lower()
    item = await db.get(SiteContent, clean_key)
    if not item:
        item = SiteContent(
            key=clean_key,
            value=payload.value,
            description=payload.description or "",
        )
        db.add(item)
    else:
        item.value = payload.value
        if payload.description is not None:
            item.description = payload.description

    await db.commit()
    await db.refresh(item)
    return item


@admin_router.post(
    "/admin/site-content/bulk",
    summary="Bulk Update Site Content Key-Values",
)
async def bulk_update_site_content(
    payload: SiteContentBulkUpdate,
    current_admin: AdminUser = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    for key, val in payload.items.items():
        clean_key = key.strip().lower()
        item = await db.get(SiteContent, clean_key)
        if not item:
            item = SiteContent(key=clean_key, value=val, description="")
            db.add(item)
        else:
            item.value = val

    await db.commit()
    return {"status": "success", "updated_count": len(payload.items)}