import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert
from pydantic import BaseModel
from app.database import get_db
from app.models.models import UserProgress, Enrollment
from app.events import publish_progress_updated

router = APIRouter(tags=["progress"])

@router.get("/enrolled")
async def list_enrolled(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    r = await db.execute(select(Enrollment.roadmap_id).where(Enrollment.user_id == uuid.UUID(user_id)))
    ids = r.scalars().all()
    return [str(rid) for rid in ids]

@router.post("/{roadmap_id}/enroll")
async def enroll(roadmap_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    stmt = insert(Enrollment).values(
        user_id=uuid.UUID(user_id),
        roadmap_id=uuid.UUID(roadmap_id),
        enrolled_at=datetime.utcnow()
    ).on_conflict_do_nothing()
    await db.execute(stmt)
    await db.commit()
    return {"ok": True}

@router.get("/{roadmap_id}/is-enrolled")
async def is_enrolled(roadmap_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    r = await db.execute(select(Enrollment).where(
        Enrollment.user_id == uuid.UUID(user_id),
        Enrollment.roadmap_id == uuid.UUID(roadmap_id)))
    return {"enrolled": r.scalar_one_or_none() is not None}

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

from typing import List, Optional

class StatsRequest(BaseModel):
    subtopic_ids: Optional[List[uuid.UUID]] = None

@router.post("/{roadmap_id}/stats")
async def get_stats(roadmap_id: str, request: Request, body: StatsRequest, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    
    conditions = [
        UserProgress.user_id == uuid.UUID(user_id),
        UserProgress.roadmap_id == uuid.UUID(roadmap_id),
        UserProgress.is_completed == True,
        UserProgress.completed_at != None
    ]
    
    if body.subtopic_ids:
        conditions.append(UserProgress.node_id.in_(body.subtopic_ids))

    stmt = (
        select(
            func.date(UserProgress.completed_at).label("date"),
            func.count(UserProgress.node_id).label("count")
        )
        .where(*conditions)
        .group_by(func.date(UserProgress.completed_at))
        .order_by(func.date(UserProgress.completed_at))
    )
    result = await db.execute(stmt)
    return [{"date": str(row.date), "count": row.count} for row in result.all() if row.date is not None]

@router.post("/{roadmap_id}/seed-test")
async def seed_test(roadmap_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    from datetime import timedelta
    # Create 5 entries for yesterday, 10 for day before
    for i in range(5):
        db.add(UserProgress(
            user_id=uuid.UUID(user_id),
            roadmap_id=uuid.UUID(roadmap_id),
            node_id=f"test-yest-{i}",
            is_completed=True,
            completed_at=datetime.utcnow() - timedelta(days=1)
        ))
    for i in range(10):
        db.add(UserProgress(
            user_id=uuid.UUID(user_id),
            roadmap_id=uuid.UUID(roadmap_id),
            node_id=f"test-day-before-{i}",
            is_completed=True,
            completed_at=datetime.utcnow() - timedelta(days=2)
        ))
    await db.commit()
    return {"status": "seeded"}

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
    await db.commit()
    
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
    await db.commit()
