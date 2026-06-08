from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_sources import source_status
from app.core.database import get_db
from app.models.entities import AgentSource
from app.schemas.api import AgentIn

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
async def list_agents(db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(AgentSource).order_by(AgentSource.name))).all()
    return {"configured": rows, "detected": source_status()}


@router.post("")
async def add_agent(payload: AgentIn, db: AsyncSession = Depends(get_db)):
    agent = AgentSource(name=payload.name, source_path=payload.source_path, enabled=payload.enabled)
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent
