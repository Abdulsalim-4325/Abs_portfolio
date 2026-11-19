from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.project import Project
from app.models.site_content import SiteContent
from app.schemas.project import ProjectResponse

public_router = APIRouter(tags=["Public Content & Projects"])


@public_router.get(
    "/projects",
    response_model=List[ProjectResponse],
    summary="List Visible Portfolio Projects (Ordered)",
)
async def list_public_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project)
        .where(Project.is_visible == True)
        .order_by(Project.display_order.asc(), Project.created_at.desc())
    )
    return result.scalars().all()


@public_router.get(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    summary="Get Specific Project Details",
)
async def get_public_project(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project or not project.is_visible:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@public_router.get(
    "/site-content",
    response_model=Dict[str, str],
    summary="Get All Public Site Content Key-Values",
)
async def get_public_site_content(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SiteContent))
    items = result.scalars().all()
    return {item.key: item.value for item in items}
