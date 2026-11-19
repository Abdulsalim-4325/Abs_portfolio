import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


def utc_now_naive() -> datetime:
    """Returns timezone-naive UTC datetime for asyncpg compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FeedbackEntry(Base):
    __tablename__ = "feedback_entries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Differentiated Person Name & Company Name in Separate Columns
    person_name: Mapped[str] = mapped_column(String(160), nullable=True, index=True)
    company_name: Mapped[str] = mapped_column(String(160), nullable=True, index=True)

    # Separate Account / Identity Columns
    email: Mapped[str] = mapped_column(String(180), nullable=True, index=True)
    insta_id: Mapped[str] = mapped_column(String(120), nullable=True, index=True)
    google_account: Mapped[str] = mapped_column(String(180), nullable=True, index=True)
    github_account: Mapped[str] = mapped_column(String(180), nullable=True, index=True)
    verification_provider: Mapped[str] = mapped_column(String(32), nullable=False)

    # Star Rating (Both Numeric 1-5 & Filled Visual Stars ★★★★★)
    rating: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    rating_stars: Mapped[str] = mapped_column(String(10), nullable=False)

    # Message (Min 10 chars, Max 1,000 words)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Telemetry & Drive Sync Status
    client_ip: Mapped[str] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(512), nullable=True)
    synced_to_drive: Mapped[bool] = mapped_column(Boolean, default=False)

    # Exact Date & Time of Message
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=utc_now_naive, nullable=False, index=True
    )


class PortfolioStats(Base):
    __tablename__ = "portfolio_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    hackathons_count: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    projects_count: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    research_papers_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=utc_now_naive, onupdate=utc_now_naive
    )