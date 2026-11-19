from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel, Field


class SiteContentItem(BaseModel):
    key: str = Field(..., max_length=100)
    value: str
    description: Optional[str] = ""
    updated_at: datetime

    class Config:
        from_attributes = True


class SiteContentUpdate(BaseModel):
    value: str
    description: Optional[str] = None


class SiteContentBulkUpdate(BaseModel):
    items: Dict[str, str]
