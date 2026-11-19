import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

from app.core.config import settings
from app.core.database import engine, Base, AsyncSessionLocal
import app.models  # Registers all models on Base.metadata
from app.core.init_db import seed_initial_data
from app.core.security import extract_client_ip, hash_ip
from app.api.routes import router as feedback_router
from app.api.admin import admin_router
from app.api.public import public_router
from app.api.analytics import analytics_router, _async_record_event


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure uploads directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # 1. Ensure all database tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. Seed initial admin user, portfolio projects, and site content
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)

    yield

    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="3.1.0",
    description="ABSCODE Full-Stack Developer Suite, CMS & Analytics Engine",
    lifespan=lifespan,
)

# CORS Configuration - Allow all local dev ports & designated origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins if "*" not in settings.cors_origins else [
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Asynchronous Analytics Middleware for Page Visits
@app.middleware("http")
async def analytics_middleware(request: Request, call_next):
    response = await call_next(request)

    path = request.url.path
    # Capture public page views while ignoring internal API polling and assets
    if (
        request.method == "GET"
        and not path.startswith(
            ("/api", "/health", "/docs", "/openapi", "/uploads", "/static", "/assets", "/favicon")
        )
        and not path.endswith((".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".webp", ".ico", ".map"))
        and response.status_code == 200
    ):
        client_ip = extract_client_ip(request)
        ip_h = hash_ip(client_ip)
        ua = request.headers.get("user-agent", "")
        ref = request.headers.get("referer", "")
        asyncio.create_task(
            _async_record_event(
                event_type="page_view",
                event_data=path,
                ip_hash=ip_h,
                user_agent=ua,
                referrer=ref,
            )
        )

    return response


# Mount Uploads directory for static image serving
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


# -----------------------------------------------------------------------------
# Include Routers with both /api and /api/v1 prefixes for seamless backward/forward compatibility
# -----------------------------------------------------------------------------
app.include_router(feedback_router)  # Existing /api/v1/auth & /api/v1/feedback

api_prefix_router = APIRouter(prefix="/api")
api_prefix_router.include_router(admin_router)
api_prefix_router.include_router(public_router)
api_prefix_router.include_router(analytics_router)

api_v1_prefix_router = APIRouter(prefix="/api/v1")
api_v1_prefix_router.include_router(admin_router)
api_v1_prefix_router.include_router(public_router)
api_v1_prefix_router.include_router(analytics_router)

app.include_router(api_prefix_router)
app.include_router(api_v1_prefix_router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "features": ["feedback", "cms", "analytics", "admin_auth"],
    }


# -----------------------------------------------------------------------------
# Dual-Port Frontend Serving: Serve HTML directly on port 8000 as well as 5500
# -----------------------------------------------------------------------------
FRONTEND_SEARCH_PATHS = [
    "/app/frontend",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "frontend"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend"),
    "./frontend",
]

_frontend_dir = None
for candidate in FRONTEND_SEARCH_PATHS:
    cand_abs = os.path.abspath(candidate)
    if os.path.exists(cand_abs) and os.path.exists(os.path.join(cand_abs, "index.html")):
        _frontend_dir = cand_abs
        break

if _frontend_dir:
    _assets_dir = os.path.join(_frontend_dir, "assets")
    if os.path.exists(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="frontend_assets")

    @app.get("/", include_in_schema=False)
    async def serve_root():
        return FileResponse(os.path.join(_frontend_dir, "index.html"))

    @app.get("/index.html", include_in_schema=False)
    async def serve_index():
        return FileResponse(os.path.join(_frontend_dir, "index.html"))

    @app.get("/abscode-command-center.html", include_in_schema=False)
    async def serve_command_center():
        return FileResponse(os.path.join(_frontend_dir, "abscode-command-center.html"))

    @app.get("/style.css", include_in_schema=False)
    async def serve_style():
        return FileResponse(os.path.join(_frontend_dir, "style.css"), media_type="text/css")

    @app.get("/script.js", include_in_schema=False)
    async def serve_script():
        return FileResponse(os.path.join(_frontend_dir, "script.js"), media_type="application/javascript")
else:
    @app.get("/", include_in_schema=False)
    async def serve_root_redirect():
        return RedirectResponse(url="http://localhost:5500/")
