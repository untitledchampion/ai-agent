"""Scenes API — CRUD for dialogue scenarios."""

from __future__ import annotations

import json
from typing import Optional, List

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from agent.models import Scene, async_session

router = APIRouter(prefix="/api/scenes", tags=["scenes"])


class SceneCreate(BaseModel):
    slug: str
    name: str
    active: bool = True
    sort_order: int = 0
    auto_reply: bool = True
    trigger: dict = {}
    fields: list[dict] = []
    tools: list[dict] = []
    response_template: str = ""
    escalate_when: list[str] = []
    knowledge: list[dict] = []


class SceneUpdate(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None
    sort_order: Optional[int] = None
    auto_reply: Optional[bool] = None
    trigger: Optional[dict] = None
    fields: Optional[List[dict]] = None
    tools: Optional[List[dict]] = None
    response_template: Optional[str] = None
    escalate_when: Optional[List[str]] = None
    knowledge: Optional[List[dict]] = None


@router.get("")
async def list_scenes():
    """List all scenarios."""
    async with async_session() as session:
        result = await session.execute(select(Scene).order_by(Scene.sort_order))
        scenes = result.scalars().all()
        return [s.to_dict() for s in scenes]


@router.get("/{slug}")
async def get_scene(slug: str):
    """Get a single scenario by slug."""
    async with async_session() as session:
        result = await session.execute(select(Scene).where(Scene.slug == slug))
        scene = result.scalar_one_or_none()
        if not scene:
            raise HTTPException(404, f"Сценарий '{slug}' не найден")
        return scene.to_dict()


@router.post("", status_code=201)
async def create_scene(data: SceneCreate):
    """Create a new scenario."""
    async with async_session() as session:
        # Check slug uniqueness
        existing = await session.execute(select(Scene).where(Scene.slug == data.slug))
        if existing.scalar_one_or_none():
            raise HTTPException(409, f"Сценарий с slug '{data.slug}' уже существует")

        scene = Scene(
            slug=data.slug,
            name=data.name,
            active=data.active,
            sort_order=data.sort_order,
            auto_reply=data.auto_reply,
            response_template=data.response_template,
        )
        scene.trigger = data.trigger
        scene.fields = data.fields
        scene.tools = data.tools
        scene.escalate_when = data.escalate_when
        scene.knowledge = data.knowledge

        session.add(scene)
        await session.commit()
        await session.refresh(scene)
        return scene.to_dict()


@router.put("/{slug}")
async def update_scene(slug: str, data: SceneUpdate):
    """Update an existing scenario."""
    async with async_session() as session:
        result = await session.execute(select(Scene).where(Scene.slug == slug))
        scene = result.scalar_one_or_none()
        if not scene:
            raise HTTPException(404, f"Сценарий '{slug}' не найден")

        if data.name is not None:
            scene.name = data.name
        if data.active is not None:
            scene.active = data.active
        if data.sort_order is not None:
            scene.sort_order = data.sort_order
        if data.auto_reply is not None:
            scene.auto_reply = data.auto_reply
        if data.trigger is not None:
            scene.trigger = data.trigger
        if data.fields is not None:
            scene.fields = data.fields
        if data.tools is not None:
            scene.tools = data.tools
        if data.response_template is not None:
            scene.response_template = data.response_template
        if data.escalate_when is not None:
            scene.escalate_when = data.escalate_when
        if data.knowledge is not None:
            scene.knowledge = data.knowledge

        await session.commit()
        await session.refresh(scene)
        return scene.to_dict()


@router.delete("/{slug}")
async def delete_scene(slug: str):
    """Delete a scenario."""
    async with async_session() as session:
        result = await session.execute(select(Scene).where(Scene.slug == slug))
        scene = result.scalar_one_or_none()
        if not scene:
            raise HTTPException(404, f"Сценарий '{slug}' не найден")
        await session.delete(scene)
        await session.commit()
        return {"status": "deleted"}
