"""Responder — generates the final response to the client.

Uses Claude Sonnet for high-quality, natural text generation.
Handles everything: answering, asking for missing data, escalation.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import anthropic

from agent.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ResponseResult:
    text: str
    should_escalate: bool = False
    escalation_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


RESPONDER_SYSTEM_PROMPT = """Ты — {persona}

{tone_block}

ТЕКУЩИЙ СЦЕНАРИЙ: {scene_name}

ИНСТРУКЦИЯ СЦЕНАРИЯ (ЭТО ТВОЯ ГЛАВНАЯ ЗАДАЧА — ВЫПОЛНЯЙ ИМЕННО ЕЁ):
{response_template}

СОБРАННЫЕ ДАННЫЕ:
{extracted_block}

{fields_block}

БАЗА ЗНАНИЙ:
{knowledge_block}

РЕЗУЛЬТАТЫ ИНСТРУМЕНТОВ:
{tools_data_block}

БАЗОВОЕ ПРАВИЛО: ты можешь оперировать ТОЛЬКО данными из разделов "БАЗА ЗНАНИЙ" и "РЕЗУЛЬТАТЫ ИНСТРУМЕНТОВ" выше. Если данных нет — НЕ ВЫДУМЫВАЙ. Не придумывай цены, остатки, адреса, сроки, телефоны.

УСЛОВИЯ ЭСКАЛАЦИИ (если любое выполняется, добавь в ответ "##ESCALATE: причина"):
{escalation_conditions}

Ответь клиенту. Следуй ИНСТРУКЦИИ СЦЕНАРИЯ. Только текст ответа, без пояснений."""


ESCALATION_CARD_TEMPLATE = """╔══════════════════════════════════════╗
║  КАРТОЧКА ДЛЯ МЕНЕДЖЕРА             ║
╠══════════════════════════════════════╣
║  Мессенджер: {messenger}
║  Чат: {chat_id}
║
║  Сценарий: {scene_name}
║  Причина: {reason}
║
║  Собранные данные:
{collected_fields}
║
║  Последние сообщения:
{recent_messages}
╚══════════════════════════════════════╝"""


async def generate_response(
    scene_config: dict,
    extracted: dict,
    tool_results: list[dict],
    history: list[dict],
    tone_config: dict,
) -> ResponseResult:
    """Генерирует ответ клиенту по контексту сценария, базе знаний и данным инструментов.

    Responder обрабатывает всё: ответы, сбор недостающих данных, эскалацию.
    """
    start = time.monotonic()

    persona = tone_config.get("persona", "")
    tone_block = tone_config.get("_prompt_block", "")

    # Format extracted data
    extracted_lines = []
    for key, value in extracted.items():
        if value is not None:
            extracted_lines.append(f"  {key}: {value}")
    extracted_block = "\n".join(extracted_lines) or "  (пока ничего не собрано)"

    # Format fields info (so LLM knows what to collect)
    fields = scene_config.get("fields", [])
    if fields:
        fields_lines = ["ПОЛЯ ДЛЯ СБОРА (если не хватает данных — задай вопрос клиенту):"]
        for f in fields:
            name = f["name"]
            required = "обязательное" if f.get("required", False) else "необязательное"
            collected = "✅" if name in extracted and extracted[name] else "❌"
            prompt = f.get("prompt", "")
            fields_lines.append(f"  {collected} {name} ({required}): {prompt}")
        fields_block = "\n".join(fields_lines)
    else:
        fields_block = ""

    # Format tool results
    tools_data_lines = []
    for tr in tool_results:
        if tr.get("success"):
            tools_data_lines.append(f"  {tr['tool_slug']}: {json.dumps(tr.get('data', {}), ensure_ascii=False)}")
        else:
            tools_data_lines.append(f"  {tr['tool_slug']}: ОШИБКА — {tr.get('error', 'unknown')}")
    tools_data_block = "\n".join(tools_data_lines) or "  (инструменты не вызывались)"

    # Format knowledge base
    knowledge_lines = []
    for entry in scene_config.get("knowledge", []):
        q = entry.get("question", "")
        a = entry.get("answer", "")
        if a:
            knowledge_lines.append(f"  В: {q}\n  О: {a}")
    knowledge_block = "\n\n".join(knowledge_lines) or "  (нет данных в базе знаний)"

    # Escalation conditions
    escalation_conditions = "\n".join(
        f"- {cond}" for cond in scene_config.get("escalate_when", [])
    ) or "  (нет условий эскалации)"

    system = RESPONDER_SYSTEM_PROMPT.format(
        persona=persona,
        tone_block=tone_block,
        scene_name=scene_config.get("name", "?"),
        response_template=scene_config.get("response_template", "Ответь клиенту."),
        extracted_block=extracted_block,
        fields_block=fields_block,
        knowledge_block=knowledge_block,
        tools_data_block=tools_data_block,
        escalation_conditions=escalation_conditions,
    )

    # Build conversation messages
    messages = []
    for msg in history[-settings.max_history_messages:]:
        role = "user" if msg.get("role") == "client" else "assistant"
        messages.append({"role": role, "content": msg.get("text", "")})

    # Ensure last message is from user
    if not messages or messages[-1]["role"] != "user":
        messages.append({"role": "user", "content": "(ожидание ответа)"})

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=settings.responder_model,
            max_tokens=2000,
            system=system,
            messages=messages,
        )

        text = response.content[0].text.strip()
        latency = int((time.monotonic() - start) * 1000)

        # Check for escalation marker
        should_escalate = "##ESCALATE" in text
        escalation_reason = ""
        if should_escalate:
            parts = text.split("##ESCALATE:")
            if len(parts) > 1:
                escalation_reason = parts[1].strip()
            text = parts[0].strip()
            if not text:
                text = "Сейчас передам ваш вопрос менеджеру, он ответит в ближайшее время."

        return ResponseResult(
            text=text,
            should_escalate=should_escalate,
            escalation_reason=escalation_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency,
        )

    except anthropic.APIError as e:
        logger.error(f"Responder API error: {e}")
        return ResponseResult(
            text="Уточню информацию и вернусь через минуту.",
            should_escalate=True,
            escalation_reason=f"API error: {e}",
            latency_ms=int((time.monotonic() - start) * 1000),
        )


def format_escalation_card(
    scene_config: dict,
    extracted: dict,
    reason: str,
    history: list[dict],
    chat_id: str = "",
    messenger: str = "test",
) -> str:
    """Format an escalation card for the manager."""
    collected_lines = []
    for key, value in extracted.items():
        if value is not None:
            collected_lines.append(f"║  ✅ {key}: {str(value)[:40]}")
    collected_block = "\n".join(collected_lines) or "║  (нет данных)"

    recent_lines = []
    for msg in history[-6:]:
        prefix = ">" if msg.get("role") == "client" else "<"
        text = msg.get("text", "")[:60]
        recent_lines.append(f"║  {prefix} {text}")
    recent_block = "\n".join(recent_lines) or "║  (нет сообщений)"

    return ESCALATION_CARD_TEMPLATE.format(
        messenger=messenger,
        chat_id=chat_id,
        scene_name=scene_config.get("name", "?"),
        reason=reason,
        collected_fields=collected_block,
        recent_messages=recent_block,
    )
