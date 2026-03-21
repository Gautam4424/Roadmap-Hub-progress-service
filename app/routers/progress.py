import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
from pydantic import BaseModel
from app.database import get_db
from app.models.models import UserProgress
from app.events import publish_progress_updated

router = APIRouter(tags=["progress"])

class ToggleRequest(BaseModel):
    node_id: uuid.UUID
    roadmap_id: uuid.UUID
    completed: bool

def get_user_id(request: Request) -> str:
    """Extract user ID from gateway-injected header."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(401, "Missing user context — request must go through gateway")
    return user_id

@router.get("/{roadmap_id}")
async def get_progress(roadmap_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    r = await db.execute(select(UserProgress).where(
        UserProgress.user_id == uuid.UUID(user_id),
        UserProgress.roadmap_id == uuid.UUID(roadmap_id)))
    items = r.scalars().all()
    return {str(p.node_id): p.is_completed for p in items}

@router.post("/toggle")
async def toggle(body: ToggleRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    stmt = insert(UserProgress).values(
        user_id=uuid.UUID(user_id), node_id=body.node_id,
        roadmap_id=body.roadmap_id, is_completed=body.completed,
        completed_at=datetime.utcnow()
    ).on_conflict_do_update(
        index_elements=["user_id", "node_id"],
        set_={"is_completed": body.completed, "completed_at": datetime.utcnow()}
    )
    await db.execute(stmt)
    
    # Publish event asynchronously (fire and forget)
    import asyncio
    asyncio.create_task(publish_progress_updated(
        user_id, str(body.node_id), str(body.roadmap_id), body.completed))
    return {"ok": True}

@router.delete("/{roadmap_id}", status_code=204)
async def reset(roadmap_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    await db.execute(delete(UserProgress).where(
        UserProgress.user_id == uuid.UUID(user_id),
        UserProgress.roadmap_id == uuid.UUID(roadmap_id)))
