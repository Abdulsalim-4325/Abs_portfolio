from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class ProjectBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    description: str = Field(..., min_length=5)
    image_url: str = Field(default="", max_length=500)
    github_url: Optional[str] = Field(default="", max_length=500)
    live_url: Optional[str] = Field(default="", max_length=500)
    tech_stack: List[str] = Field(default_factory=list)
    display_order: int = Field(default=0)
    is_visible: bool = Field(default=True)


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=200)
    description: Optional[str] = Field(default=None, min_length=5)
    image_url: Optional[str] = Field(default=None, max_length=500)
    github_url: Optional[str] = Field(default=None, max_length=500)
    live_url: Optional[str] = Field(default=None, max_length=500)
    tech_stack: Optional[List[str]] = None
    display_order: Optional[int] = None
    is_visible: Optional[bool] = None


class ProjectResponse(ProjectBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
