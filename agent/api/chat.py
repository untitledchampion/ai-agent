"""Chat API — test chat and message processing endpoints."""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from agent.models import Conversation, ConversationMessage, async_session
from agent.core.pipeline import process_message, PipelineResult

router = APIRouter(prefix="/api/chat", tags=["chat"])


class SendMessageRequest(BaseModel):
    chat_id: str = "test-chat-1"
    message: str
    messenger_type: str = "test"


class SendMessageResponse(BaseModel):
    response: str
    scene_slug: Optional[str] = None
    scene_name: Optional[str] = None
    confidence: float = 0.0
    action: str = ""
    escalation_card: str = ""

    # Debug
    triage: dict = {}
    scene_decision: str = ""
    tools_results: list[dict] = []
    scene_data: dict = {}

    # Metrics
    latency_ms: int = 0
    classifier_tokens: int = 0
    responder_tokens: int = 0
    cost_usd: float = 0.0


@router.post("/send", response_model=SendMessageResponse)
async def send_message(req: SendMessageRequest):
    """Send a message as a client and get agent response."""
    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty")

    result = await process_message(
        chat_id=req.chat_id,
        message=req.message.strip(),
        messenger_type=req.messenger_type,
    )

    return SendMessageResponse(
        response=result.response_text,
        scene_slug=result.scene_slug,
        scene_name=result.scene_name,
        confidence=result.confidence,
        action=result.action,
        escalation_card=result.escalation_card,
        triage=result.triage_result,
        scene_decision=result.scene_decision,
        tools_results=result.tools_results,
        scene_data=result.scene_data,
        latency_ms=result.total_latency_ms,
        classifier_tokens=result.classifier_tokens,
        responder_tokens=result.responder_tokens,
        cost_usd=result.total_cost_usd,
    )


@router.post("/stream")
async def stream_message(req: SendMessageRequest):
    """SSE streaming variant of /send. Emits triage, tools, done events."""
    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty")

    queue: asyncio.Queue = asyncio.Queue()
    SENTINEL = object()

    async def emit(payload):
        await queue.put(payload)

    async def worker():
        try:
            result = await process_message(
                chat_id=req.chat_id,
                message=req.message.strip(),
                messenger_type=req.messenger_type,
                emit=emit,
            )
            await queue.put({
                "type": "done",
                "response": result.response_text,
                "scene_slug": result.scene_slug,
                "scene_name": result.scene_name,
                "confidence": result.confidence,
                "action": result.action,
                "escalation_card": result.escalation_card,
                "triage": result.triage_result,
                "scene_decision": result.scene_decision,
                "tools_results": result.tools_results,
                "scene_data": result.scene_data,
                "latency_ms": result.total_latency_ms,
                "classifier_tokens": result.classifier_tokens,
                "responder_tokens": result.responder_tokens,
                "cost_usd": result.total_cost_usd,
            })
        except Exception as e:
            await queue.put({"type": "error", "error": str(e)})
        finally:
            await queue.put(SENTINEL)

    async def sse():
        task = asyncio.create_task(worker())
        try:
            while True:
                item = await queue.get()
                if item is SENTINEL:
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


@router.get("/conversations")
async def list_conversations():
    """List all test conversations."""
    async with async_session() as session:
        result = await session.execute(
            select(Conversation).order_by(Conversation.updated_at.desc())
        )
        convs = result.scalars().all()
        return [
            {
                "id": c.id,
                "chat_id": c.chat_id,
                "messenger_type": c.messenger_type,
                "current_scene": c.current_scene,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in convs
        ]


@router.get("/conversations/{chat_id}")
async def get_conversation(chat_id: str):
    """Get full conversation with messages."""
    async with async_session() as session:
        result = await session.execute(
            select(Conversation)
            .where(Conversation.chat_id == chat_id)
            .options(selectinload(Conversation.messages))
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(404, f"Conversation '{chat_id}' not found")
        return conv.to_dict()


@router.delete("/conversations/{chat_id}")
async def delete_conversation(chat_id: str):
    """Delete a conversation and all its messages (reset chat)."""
    async with async_session() as session:
        result = await session.execute(
            select(Conversation).where(Conversation.chat_id == chat_id)
        )
        conv = result.scalar_one_or_none()
        if conv:
            await session.execute(
                delete(ConversationMessage).where(
                    ConversationMessage.conversation_id == conv.id
                )
            )
            await session.delete(conv)
            await session.commit()
            return {"status": "deleted"}
        raise HTTPException(404, f"Conversation '{chat_id}' not found")
