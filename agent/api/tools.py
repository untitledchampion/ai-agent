"""Tools API — CRUD for tool registry."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from agent.models import Tool, async_session

router = APIRouter(prefix="/api/tools", tags=["tools"])


class ToolCreate(BaseModel):
    slug: str
    name: str
    description: str = ""
    active: bool = True
    request: dict = {}
    response_mapping: dict = {}
    fallback_message: str = "Не удалось получить данные. Уточню у менеджера."
    timeout_ms: int = 5000
    retry_count: int = 1


class ToolUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None
    request: Optional[dict] = None
    response_mapping: Optional[dict] = None
    fallback_message: Optional[str] = None
    timeout_ms: Optional[int] = None
    retry_count: Optional[int] = None


@router.get("")
async def list_tools():
    """List all tools."""
    async with async_session() as session:
        result = await session.execute(select(Tool).order_by(Tool.slug))
        tools = result.scalars().all()
        return [t.to_dict() for t in tools]


@router.get("/{slug}")
async def get_tool(slug: str):
    """Get a single tool by slug."""
    async with async_session() as session:
        result = await session.execute(select(Tool).where(Tool.slug == slug))
        tool = result.scalar_one_or_none()
        if not tool:
            raise HTTPException(404, f"Tool '{slug}' not found")
        return tool.to_dict()


@router.post("", status_code=201)
async def create_tool(data: ToolCreate):
    """Create a new tool."""
    async with async_session() as session:
        existing = await session.execute(select(Tool).where(Tool.slug == data.slug))
        if existing.scalar_one_or_none():
            raise HTTPException(409, f"Tool with slug '{data.slug}' already exists")

        tool = Tool(
            slug=data.slug,
            name=data.name,
            description=data.description,
            active=data.active,
            fallback_message=data.fallback_message,
            timeout_ms=data.timeout_ms,
            retry_count=data.retry_count,
        )
        tool.request_config = data.request
        tool.response_mapping = data.response_mapping

        session.add(tool)
        await session.commit()
        await session.refresh(tool)
        return tool.to_dict()


@router.put("/{slug}")
async def update_tool(slug: str, data: ToolUpdate):
    """Update a tool."""
    async with async_session() as session:
        result = await session.execute(select(Tool).where(Tool.slug == slug))
        tool = result.scalar_one_or_none()
        if not tool:
            raise HTTPException(404, f"Tool '{slug}' not found")

        if data.name is not None:
            tool.name = data.name
        if data.description is not None:
            tool.description = data.description
        if data.active is not None:
            tool.active = data.active
        if data.request is not None:
            tool.request_config = data.request
        if data.response_mapping is not None:
            tool.response_mapping = data.response_mapping
        if data.fallback_message is not None:
            tool.fallback_message = data.fallback_message
        if data.timeout_ms is not None:
            tool.timeout_ms = data.timeout_ms
        if data.retry_count is not None:
            tool.retry_count = data.retry_count

        await session.commit()
        await session.refresh(tool)
        return tool.to_dict()


@router.delete("/{slug}")
async def delete_tool(slug: str):
    """Delete a tool."""
    async with async_session() as session:
        result = await session.execute(select(Tool).where(Tool.slug == slug))
        tool = result.scalar_one_or_none()
        if not tool:
            raise HTTPException(404, f"Tool '{slug}' not found")
        await session.delete(tool)
        await session.commit()
        return {"status": "deleted"}
