from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Request, BackgroundTasks, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, AsyncSessionLocal
from app.core.security import (
    hash_ip,
    extract_client_ip,
    verify_admin_token,
)
from app.models.admin import AdminUser
from app.models.analytics import AnalyticsEvent
from app.models.feedback import FeedbackEntry
from app.schemas.analytics import (
    AnalyticsEventCreate,
    AnalyticsEventResponse,
    AnalyticsSummaryResponse,
    VisitorDayTrend,
    ProjectClickMetric,
)

analytics_router = APIRouter(tags=["Analytics Tracking Engine"])


async def _async_record_event(
    event_type: str,
    event_data: str | None,
    ip_hash: str,
    user_agent: str | None,
    referrer: str | None,
):
    """Background helper to commit an analytics event without delaying response."""
    async with AsyncSessionLocal() as session:
        try:
            event = AnalyticsEvent(
                event_type=event_type,
                event_data=event_data,
                ip_hash=ip_hash,
                user_agent=user_agent[:512] if user_agent else None,
                referrer=referrer[:512] if referrer else None,
            )
            session.add(event)
            await session.commit()
        except Exception as e:
            await session.rollback()
            print(f"[ANALYTICS ERROR] Could not record event: {e}", flush=True)


@analytics_router.post(
    "/analytics/event",
    response_model=AnalyticsEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record Frontend Analytics Beacon Event",
)
async def record_analytics_event(
    payload: AnalyticsEventCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    client_ip = extract_client_ip(request)
    client_ip_hash = hash_ip(client_ip)
    ua = request.headers.get("user-agent", "")[:512]
    ref = payload.referrer or request.headers.get("referer", "")[:512]

    # Use background task for sub-millisecond beacon turnaround
    background_tasks.add_task(
        _async_record_event,
        payload.event_type.strip(),
        (payload.event_data.strip() if payload.event_data else None),
        client_ip_hash,
        ua,
        ref,
    )

    return AnalyticsEventResponse(status="recorded")


@analytics_router.get(
    "/analytics/summary",
    response_model=AnalyticsSummaryResponse,
    summary="Get 30-Day Aggregated Analytics & KPIs (Admin Only)",
)
async def get_analytics_summary(
    current_admin: AdminUser = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    thirty_days_ago = now - timedelta(days=30)

    # 1. Total page views in the last 30 days
    pv_result = await db.execute(
        select(func.count(AnalyticsEvent.id)).where(
            and_(
                AnalyticsEvent.timestamp >= thirty_days_ago,
                AnalyticsEvent.event_type == "page_view",
            )
        )
    )
    total_pageviews_30d = pv_result.scalar() or 0

    # 2. Total unique visitors in the last 30 days
    uv_result = await db.execute(
        select(func.count(func.distinct(AnalyticsEvent.ip_hash))).where(
            AnalyticsEvent.timestamp >= thirty_days_ago
        )
    )
    unique_visitors_30d = uv_result.scalar() or 0

    # 3. Returning visitors in the last 30 days
    # (IPs that have appeared with > 1 event in the period)
    subq = (
        select(AnalyticsEvent.ip_hash)
        .where(AnalyticsEvent.timestamp >= thirty_days_ago)
        .group_by(AnalyticsEvent.ip_hash)
        .having(func.count(AnalyticsEvent.id) > 1)
        .subquery()
    )
    ret_result = await db.execute(select(func.count()).select_from(subq))
    returning_visitors_30d = ret_result.scalar() or 0

    # 4. Daily trends for the last 30 days
    daily_trends: List[VisitorDayTrend] = []
    # Build dictionary of all 30 days initialized to 0
    days_map: Dict[str, Dict[str, int]] = {}
    for i in range(29, -1, -1):
        day_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        days_map[day_str] = {"views": 0, "uniques": set()}

    events_30d = await db.execute(
        select(
            AnalyticsEvent.timestamp,
            AnalyticsEvent.event_type,
            AnalyticsEvent.ip_hash,
        ).where(AnalyticsEvent.timestamp >= thirty_days_ago)
    )
    for ts, ev_type, ip_h in events_30d.all():
        d_str = ts.strftime("%Y-%m-%d")
        if d_str in days_map:
            if ev_type == "page_view":
                days_map[d_str]["views"] += 1
            days_map[d_str]["uniques"].add(ip_h)

    for d_str, val in sorted(days_map.items()):
        daily_trends.append(
            VisitorDayTrend(
                date=d_str,
                page_views=val["views"],
                unique_visitors=len(val["uniques"]),
            )
        )

    # 5. Most-clicked projects (top 8)
    proj_result = await db.execute(
        select(AnalyticsEvent.event_data, func.count(AnalyticsEvent.id).label("cnt"))
        .where(
            and_(
                AnalyticsEvent.timestamp >= thirty_days_ago,
                AnalyticsEvent.event_type == "project_click",
                AnalyticsEvent.event_data != None,
            )
        )
        .group_by(AnalyticsEvent.event_data)
        .order_by(func.count(AnalyticsEvent.id).desc())
        .limit(8)
    )
    most_clicked_projects = [
        ProjectClickMetric(project_title=row[0] or "Unknown", clicks=row[1])
        for row in proj_result.all()
    ]

    # 6. Events by event_type
    type_result = await db.execute(
        select(AnalyticsEvent.event_type, func.count(AnalyticsEvent.id))
        .where(AnalyticsEvent.timestamp >= thirty_days_ago)
        .group_by(AnalyticsEvent.event_type)
    )
    events_by_type = {row[0]: row[1] for row in type_result.all()}

    # 7. Total feedback metrics from feedback_entries table
    fb_total_res = await db.execute(select(func.count(FeedbackEntry.id)))
    fb_total = fb_total_res.scalar() or 0

    fb_avg_res = await db.execute(select(func.avg(FeedbackEntry.rating)))
    fb_avg_raw = fb_avg_res.scalar()
    fb_avg = round(float(fb_avg_raw), 2) if fb_avg_raw is not None else 0.0

    fb_ratings_res = await db.execute(
        select(FeedbackEntry.rating, func.count(FeedbackEntry.id))
        .group_by(FeedbackEntry.rating)
        .order_by(FeedbackEntry.rating.desc())
    )
    fb_ratings_dist = {str(row[0]): row[1] for row in fb_ratings_res.all()}

    feedback_metrics = {
        "total_count": fb_total,
        "average_rating": fb_avg,
        "rating_distribution": fb_ratings_dist,
    }

    return AnalyticsSummaryResponse(
        total_pageviews_30d=total_pageviews_30d,
        unique_visitors_30d=unique_visitors_30d,
        returning_visitors_30d=returning_visitors_30d,
        daily_trends=daily_trends,
        most_clicked_projects=most_clicked_projects,
        events_by_type=events_by_type,
        feedback_metrics=feedback_metrics,
    )
