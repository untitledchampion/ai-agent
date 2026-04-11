"""Agent Pipeline — orchestrates the full message processing flow.

Triage (action + scene) → Tools (if needed) → Responder
Agent works ONLY through configured scenarios. No scenario = no response.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from agent.config import settings
from agent.models import (
    Scene,
    ToneConfig,
    Conversation,
    ConversationMessage,
    AgentMetric,
    async_session,
)
from .triage import triage, TriageResult
from .tool_executor import execute_tools, determine_tools_to_call, ToolResult
from .responder import (
    generate_response,
    format_escalation_card,
    ResponseResult,
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Full result of processing a client message."""

    response_text: str
    scene_slug: str | None = None
    scene_name: str | None = None
    confidence: float = 0.0
    action: str = ""  # "auto_reply", "escalation", "resolved", "no_match"
    escalation_card: str = ""

    # Debug info
    triage_result: dict = field(default_factory=dict)
    scene_decision: str = ""
    tools_results: list[dict] = field(default_factory=list)
    scene_data: dict = field(default_factory=dict)

    # Metrics
    total_latency_ms: int = 0
    classifier_tokens: int = 0
    responder_tokens: int = 0
    total_cost_usd: float = 0.0


async def process_message(
    chat_id: str,
    message: str,
    messenger_type: str = "test",
) -> PipelineResult:
    """Process a single client message through the pipeline.

    Flow: Triage → Tools (optional) → Responder
    No matching scenario = no response (action="no_match").
    """
    start = time.monotonic()
    result = PipelineResult(response_text="")

    async with async_session() as session:
        # ── 1. Load configuration ──
        scenes = await _load_active_scenes(session)
        tone = await _load_tone(session)
        tone_dict = tone.to_dict() if tone else {"persona": "", "parameters": {}, "rules": [], "examples": [], "forbidden_phrases": [], "_prompt_block": ""}
        tone_dict["_prompt_block"] = tone.to_prompt_block() if tone else ""

        # ── 2. Load or create conversation ──
        conversation = await _get_or_create_conversation(
            session, chat_id, messenger_type
        )
        history = [m.to_dict() for m in conversation.messages]

        # Save client message
        client_msg = ConversationMessage(
            conversation_id=conversation.id,
            role="client",
            text=message,
        )
        session.add(client_msg)
        await session.flush()

        # ── 3. No active scenes = no response ──
        if not scenes:
            result.action = "no_match"
            result.total_latency_ms = int((time.monotonic() - start) * 1000)
            await _save_metric(session, chat_id, result, start)
            await session.commit()
            return result

        # ── 4. Triage — single LLM call decides everything ──
        scene_dicts = [s.to_dict() for s in scenes]
        triage_result = await triage(message, history, scene_dicts)

        result.triage_result = {
            "action": triage_result.action,
            "scene": triage_result.scene,
            "confidence": triage_result.confidence,
            "extracted": triage_result.extracted,
            "reason": triage_result.reason,
        }
        result.scene_slug = triage_result.scene
        result.confidence = triage_result.confidence
        result.scene_decision = triage_result.action.lower()
        result.classifier_tokens = triage_result.input_tokens + triage_result.output_tokens

        # ── 5. Find the matching scene ──
        scene_config = None
        if triage_result.scene:
            for s in scene_dicts:
                if s["slug"] == triage_result.scene:
                    scene_config = s
                    break

        # ── 6. Continue current scene if triage is uncertain ──
        # If conversation already has an active scene and triage couldn't
        # confidently pick a different one — stay in the current scene.
        current_scene_slug = conversation.current_scene
        if not scene_config and current_scene_slug:
            for s in scene_dicts:
                if s["slug"] == current_scene_slug:
                    scene_config = s
                    triage_result.action = "SELF"
                    result.scene_slug = current_scene_slug
                    result.triage_result["continued_from"] = current_scene_slug
                    logger.info(
                        "Triage uncertain (scene=%s, conf=%.2f) — continuing current scene '%s'",
                        triage_result.scene, triage_result.confidence, current_scene_slug,
                    )
                    break

        # ── 7. No matching scene = no response ──
        if not scene_config:
            result.action = "no_match"
            result.total_latency_ms = int((time.monotonic() - start) * 1000)
            await _save_metric(session, chat_id, result, start)
            await session.commit()
            return result

        # ── 7. SELF — agent handles it through the scenario ──
        result.scene_name = scene_config.get("name", "")
        result.scene_slug = scene_config.get("slug", triage_result.scene)

        # Merge extracted data with previous conversation data
        prev_data = conversation.scene_data if conversation.current_scene == triage_result.scene else {}
        extracted = {**prev_data, **triage_result.extracted}
        result.scene_data = extracted

        # Update conversation state
        conversation.current_scene = result.scene_slug
        conversation.scene_data = extracted

        # Check if scene requires manager (auto_reply=false)
        if not scene_config.get("auto_reply", True):
            result.action = "escalation"
        else:
            result.action = "auto_reply"

        # ── 8. Execute tools if needed ──
        tool_results_list = []
        tools_to_call = determine_tools_to_call(scene_config, extracted)
        if tools_to_call:
            tool_results = await execute_tools(
                tools_to_call=tools_to_call,
                scene_data=extracted,
            )
            tool_results_list = [
                {
                    "tool_slug": tr.tool_slug,
                    "success": tr.success,
                    "data": tr.data,
                    "error": tr.error,
                    "latency_ms": tr.latency_ms,
                }
                for tr in tool_results
            ]
            result.tools_results = tool_results_list

        # ── 9. Generate response ──
        resp = await generate_response(
            scene_config=scene_config,
            extracted=extracted,
            tool_results=tool_results_list,
            history=history + [{"role": "client", "text": message}],
            tone_config=tone_dict,
        )
        result.response_text = resp.text
        result.responder_tokens = resp.input_tokens + resp.output_tokens

        # Check if responder triggered escalation
        if resp.should_escalate:
            result.action = "escalation"
            result.escalation_card = format_escalation_card(
                scene_config=scene_config,
                extracted=extracted,
                reason=resp.escalation_reason,
                history=history + [{"role": "client", "text": message}],
                chat_id=chat_id,
                messenger=messenger_type,
            )

        # ── 10. Save and return ──
        result.total_latency_ms = int((time.monotonic() - start) * 1000)
        result.total_cost_usd = _calc_cost(result.classifier_tokens, result.responder_tokens)

        await _save_agent_response(session, conversation, result)
        await _save_metric(session, chat_id, result, start)
        await session.commit()

    return result


# ── Helper functions ─────────────────────────────────────────────────


async def _load_active_scenes(session) -> list[Scene]:
    """Load all active scenes ordered by sort_order."""
    result = await session.execute(
        select(Scene).where(Scene.active == True).order_by(Scene.sort_order)
    )
    return list(result.scalars().all())


async def _load_tone(session) -> ToneConfig | None:
    """Load the first (active) tone config."""
    result = await session.execute(select(ToneConfig).limit(1))
    return result.scalar_one_or_none()


async def _get_or_create_conversation(
    session, chat_id: str, messenger_type: str,
) -> Conversation:
    """Get existing conversation or create new one."""
    result = await session.execute(
        select(Conversation)
        .where(Conversation.chat_id == chat_id)
        .options(selectinload(Conversation.messages))
    )
    conv = result.scalar_one_or_none()

    if conv is None:
        conv = Conversation(
            chat_id=chat_id,
            messenger_type=messenger_type,
        )
        session.add(conv)
        await session.flush()
        result = await session.execute(
            select(Conversation)
            .where(Conversation.id == conv.id)
            .options(selectinload(Conversation.messages))
        )
        conv = result.scalar_one()

    return conv


async def _save_agent_response(
    session, conversation: Conversation, result: PipelineResult,
) -> None:
    """Save agent's response as a conversation message."""
    if not result.response_text:
        return
    agent_msg = ConversationMessage(
        conversation_id=conversation.id,
        role="agent",
        text=result.response_text,
        scene_slug=result.scene_slug,
        confidence=result.confidence,
        tools_called_json=json.dumps(result.tools_results, ensure_ascii=False),
        debug_json=json.dumps({
            "triage": result.triage_result,
            "scene_decision": result.scene_decision,
            "action": result.action,
            "scene_data": result.scene_data,
            "latency_ms": result.total_latency_ms,
            "cost_usd": result.total_cost_usd,
        }, ensure_ascii=False),
    )
    session.add(agent_msg)


async def _save_metric(
    session, chat_id: str, result: PipelineResult, start: float,
) -> None:
    """Save metric for analytics."""
    metric = AgentMetric(
        chat_id=chat_id,
        scene_slug=result.scene_slug,
        action=result.action,
        confidence=result.confidence,
        classifier_tokens=result.classifier_tokens,
        responder_tokens=result.responder_tokens,
        total_cost_usd=result.total_cost_usd,
        latency_ms=int((time.monotonic() - start) * 1000),
    )
    session.add(metric)


def _calc_cost(classifier_tokens: int, responder_tokens: int) -> float:
    """Estimate LLM API cost in USD (Sonnet pricing)."""
    input_cost = classifier_tokens * 0.000003
    output_cost = responder_tokens * 0.000015
    return round(input_cost + output_cost, 6)
