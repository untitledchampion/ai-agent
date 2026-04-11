"""Tone API — manage agent voice/tone settings."""

from __future__ import annotations

from typing import Optional, List

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from agent.models import ToneConfig, async_session

router = APIRouter(prefix="/api/tone", tags=["tone"])


class ToneUpdate(BaseModel):
    persona: Optional[str] = None
    parameters: Optional[dict] = None
    rules: Optional[List[str]] = None
    examples: Optional[List[dict]] = None
    forbidden_phrases: Optional[List[str]] = None


@router.get("")
async def get_tone():
    """Get current tone config."""
    async with async_session() as session:
        result = await session.execute(select(ToneConfig).limit(1))
        tone = result.scalar_one_or_none()
        if not tone:
            return {
                "id": None,
                "name": "default",
                "persona": "",
                "parameters": {},
                "rules": [],
                "examples": [],
                "forbidden_phrases": [],
            }
        return tone.to_dict()


@router.put("")
async def update_tone(data: ToneUpdate):
    """Update tone config (creates if not exists)."""
    async with async_session() as session:
        result = await session.execute(select(ToneConfig).limit(1))
        tone = result.scalar_one_or_none()

        if not tone:
            tone = ToneConfig(name="default")
            session.add(tone)

        if data.persona is not None:
            tone.persona = data.persona
        if data.parameters is not None:
            tone.parameters = data.parameters
            flag_modified(tone, "parameters_json")
        if data.rules is not None:
            tone.rules = data.rules
            flag_modified(tone, "rules_json")
        if data.examples is not None:
            tone.examples = data.examples
            flag_modified(tone, "examples_json")
        if data.forbidden_phrases is not None:
            tone.forbidden_phrases = data.forbidden_phrases
            flag_modified(tone, "forbidden_phrases_json")

        await session.commit()
        await session.refresh(tone)
        return tone.to_dict()


@router.get("/preview")
async def preview_tone_prompt():
    """Preview the tone block as it will appear in the LLM prompt."""
    async with async_session() as session:
        result = await session.execute(select(ToneConfig).limit(1))
        tone = result.scalar_one_or_none()
        if not tone:
            return {"prompt_block": "(нет настроек тона)"}
        return {"prompt_block": tone.to_prompt_block()}
