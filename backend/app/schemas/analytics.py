from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class AnalyticsEventCreate(BaseModel):
    event_type: str = Field(..., max_length=50)  # page_view, project_click, social_click, resume_download
    event_data: Optional[str] = Field(default=None, max_length=255)
    referrer: Optional[str] = Field(default=None, max_length=512)


class AnalyticsEventResponse(BaseModel):
    status: str = "recorded"
    id: Optional[str] = None


class VisitorDayTrend(BaseModel):
    date: str
    page_views: int
    unique_visitors: int


class ProjectClickMetric(BaseModel):
    project_title: str
    clicks: int


class AnalyticsSummaryResponse(BaseModel):
    total_pageviews_30d: int
    unique_visitors_30d: int
    returning_visitors_30d: int
    daily_trends: List[VisitorDayTrend]
    most_clicked_projects: List[ProjectClickMetric]
    events_by_type: Dict[str, int]
    feedback_metrics: Dict[str, Any]
