from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.admin import AdminUser
from app.models.project import Project
from app.models.site_content import SiteContent


async def seed_initial_data(session: AsyncSession) -> None:
    """Seeds default admin user, initial portfolio projects, and site content."""
    # 1. Seed or Update Dedicated Admin User (salim / Abdul@4325)
    target_username = settings.ADMIN_USERNAME.lower().strip()
    admin_result = await session.execute(
        select(AdminUser).where(AdminUser.username == target_username)
    )
    user = admin_result.scalar_one_or_none()
    if not user:
        user = AdminUser(
            username=target_username,
            hashed_password=hash_password(settings.ADMIN_DEFAULT_PASSWORD),
        )
        session.add(user)
        print(f"[STARTUP] Initialized admin user: '{target_username}'", flush=True)
    else:
        user.hashed_password = hash_password(settings.ADMIN_DEFAULT_PASSWORD)
        print(f"[STARTUP] Synchronized password for admin user: '{target_username}'", flush=True)

    # Clean up any legacy default admin accounts so only the requested user exists
    await session.execute(
        delete(AdminUser).where(AdminUser.username != target_username)
    )

    # 2. Seed Default Site Content if Empty
    content_result = await session.execute(select(SiteContent))
    if not content_result.scalars().first():
        default_contents = [
            ("hero_greeting", "Hello, I'm", "Hero section small cursive greeting"),
            ("hero_name", "ABDUL\nSALIM", "Hero section display name"),
            ("hero_roles", "BACKEND SYSTEMS ENGINEER, DISTRIBUTED SYSTEMS ARCHITECT, CLOUD & API SPECIALIST", "Comma-separated rotating roles"),
            ("hero_description", "I architect and build resilient, high-throughput backend systems, distributed APIs, and cryptographic security frameworks. Passionate about clean microservice architecture, asynchronous processing, and engineering precision that scales.", "Hero paragraph bio"),
            ("stat_hackathons", "03", "Number of hackathons participated"),
            ("stat_projects", "06", "Number of projects architected"),
            ("stat_papers", "01+", "Number of research publications"),
            ("resume_url", "https://github.com/AbdulSalim-4325", "Direct link to download or view resume"),
            ("quote_body", "Good engineering is not just how fast it runs in dev, but how resiliently it holds under production pressure.", "Hero quote banner text"),
            ("quote_author", "Abdul Salim", "Hero quote signature"),
            ("contact_email", "abdulsalim432005@gmail.com", "Contact email address"),
            ("contact_whatsapp", "https://wa.me/919038807851", "WhatsApp direct link"),
            ("contact_linkedin", "https://www.linkedin.com/in/abdul-salim-engineer", "LinkedIn profile link"),
            ("contact_github", "https://github.com/AbdulSalim-4325", "GitHub profile link"),
            ("contact_instagram", "https://www.instagram.com/_absalim__/", "Instagram profile link"),
        ]
        for key, val, desc in default_contents:
            session.add(SiteContent(key=key, value=val, description=desc))
        print("[STARTUP] Initialized default site content key-values.", flush=True)

    # 3. Seed Existing Portfolio Projects if Empty
    proj_result = await session.execute(select(Project))
    if not proj_result.scalars().first():
        default_projects = [
            Project(
                title="V.A.L.A.R. AI RUNTIME",
                description="Autonomous Alexa & MCP agent core powered by AWS Bedrock Runtime and FastAPI.",
                image_url="./assets/VALAAR_Image.png",
                live_url="https://valar-runtime.vercel.app",
                github_url="https://github.com/AbdulSalim-4325",
                tech_stack=["AWS Bedrock", "FastAPI", "MCP", "Python"],
                display_order=1,
                is_visible=True,
            ),
            Project(
                title="ATERS EMERGENCY RESPONSE",
                description="Real-time ambulance tracking and automated hospital dispatch system.",
                image_url="./assets/ATERS_Image.png",
                live_url="https://ater-vjpu.onrender.com",
                github_url="https://github.com/AbdulSalim-4325",
                tech_stack=["FastAPI", "WebSockets", "Leaflet.js", "Redis"],
                display_order=2,
                is_visible=True,
            ),
            Project(
                title="STIX 2.1 THREAT ENGINE",
                description="Automated cyber threat intelligence aggregator and STIX 2.1 normalization pipeline.",
                image_url="./assets/THREAT_ENGINE_Image.png",
                live_url="https://threat-intel-dashboard-cmxjf9fsgwi7hv7trk6xca.streamlit.app",
                github_url="https://github.com/AbdulSalim-4325",
                tech_stack=["STIX 2.1", "Python", "Streamlit", "PostgreSQL"],
                display_order=3,
                is_visible=True,
            ),
            Project(
                title="B2B FEEDBACK ANALYTICS API",
                description="High-throughput asynchronous feedback ingestion engine using FastAPI, Celery, and Redis.",
                image_url="https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=800&q=80",
                live_url="https://b2b-feedback-analytics.onrender.com",
                github_url="https://github.com/AbdulSalim-4325",
                tech_stack=["FastAPI", "Celery", "Redis", "PostgreSQL"],
                display_order=4,
                is_visible=True,
            ),
            Project(
                title="FEATURE FLAG ROUTING API",
                description="OpenFeature-compliant routing engine with sub-millisecond Redis caching and PostgreSQL audit logs.",
                image_url="./assets/Webhook_dispatcher_image.jpg",
                live_url="https://feature-flag-routing.onrender.com",
                github_url="https://github.com/AbdulSalim-4325",
                tech_stack=["OpenFeature", "Redis", "PostgreSQL", "Docker"],
                display_order=5,
                is_visible=True,
            ),
        ]
        for p in default_projects:
            session.add(p)
        print("[STARTUP] Seeded 5 initial portfolio projects into database.", flush=True)

    await session.commit()
