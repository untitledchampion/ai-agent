"""Triage — classifies client messages and decides action.

Single LLM call that determines:
- action: SELF (agent answers) / ESCALATE (pass to manager) / RESOLVED (client done)
- scene: which scenario to use
- extracted: data parsed from message
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
class TriageResult:
    action: str  # "SELF" | "ESCALATE" | "RESOLVED"
    scene: str | None  # scene slug
    confidence: float
    extracted: dict = field(default_factory=dict)
    reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


TRIAGE_PROMPT = """Ты — классификатор сообщений клиентов компании ОптСилинг (B2B продажа материалов для натяжных потолков).

Задача: определи действие и подходящий сценарий для входящего сообщения.

Последнее сообщение клиента: {message}

Контекст диалога:
{context}

Доступные сценарии:
{scenarios_block}

Верни ТОЛЬКО JSON (без markdown, без пояснений):
{{
  "scene": "slug сценария из списка выше или null если ни один не подходит",
  "confidence": 0.0-1.0,
  "action": "SELF | ESCALATE | RESOLVED",
  "extracted": {{
    ...ТОЛЬКО поля, определённые в выбранном сценарии (см. "Поля:" у каждого сценария)...
  }},
  "reason": "краткое пояснение на русском"
}}

ПРАВИЛА:
1. action = SELF — если есть подходящий сценарий и агент может помочь (приветствие, вопрос, заказ, наличие и т.д.)
2. action = ESCALATE — ТОЛЬКО если: ни один сценарий не подходит, клиент требует живого человека, или ситуация экстренная
3. action = RESOLVED — если клиент даёт понять что вопрос закрыт ("спасибо", "помогло", "всё, разобрался")
4. Если уверенность < 0.7 — ставь ESCALATE (кроме RESOLVED)
5. ВАЖНО: жалобы, возвраты, вопросы по оплате — это НЕ причина для ESCALATE. Агент сначала собирает данные по сценарию!
6. Приветствия ("добрый день", "привет", "здравствуйте") — это SELF + сценарий faq
7. В extracted указывай ТОЛЬКО поля из определения выбранного сценария (раздел "Поля:"). НЕ выдумывай свои поля вроде request_type, urgency и т.д.
8. Если у сценария нет полей — extracted должен быть пустым объектом {{}}"""


def _build_scenarios_block(scenes: list[dict]) -> str:
    """Format scenes list for the triage prompt, including field definitions."""
    lines = []
    for s in scenes:
        trigger = s.get("trigger", {})
        line = f"  {s['slug']} ({s['name']}): {trigger.get('description', '')}"
        examples = trigger.get("examples", [])
        if examples:
            line += f" | Примеры: {'; '.join(examples[:3])}"
        if not s.get("auto_reply", True):
            line += " [ТРЕБУЕТ МЕНЕДЖЕРА]"
        lines.append(line)
        # Show field definitions with descriptions so LLM knows what to extract
        fields = s.get("fields", [])
        if fields:
            lines.append("    Поля для извлечения:")
            for f in fields:
                fname = f.get("name", "")
                fprompt = f.get("prompt", "")
                req = " (обязательное)" if f.get("required") else ""
                lines.append(f"      - {fname}{req}: {fprompt}")
    return "\n".join(lines) or "  (нет активных сценариев — нужна эскалация)"


def _build_context(history: list[dict]) -> str:
    """Format conversation history for triage."""
    if not history:
        return "нет контекста (первое сообщение)"
    lines = []
    for msg in history[-5:]:
        role = "Клиент" if msg.get("role") == "client" else "Менеджер"
        lines.append(f"{role}: {msg.get('text', '')}")
    return "\n".join(lines)


async def triage(
    message: str,
    history: list[dict],
    scenes: list[dict],
) -> TriageResult:
    """Classify a client message and decide action.

    Returns TriageResult with action (SELF/ESCALATE/RESOLVED),
    scene slug, confidence, and extracted data.
    """
    start = time.monotonic()

    scenarios_block = _build_scenarios_block(scenes)
    context = _build_context(history)

    prompt = TRIAGE_PROMPT.format(
        message=message,
        context=context,
        scenarios_block=scenarios_block,
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=settings.classifier_model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.content[0].text.strip()

        # Extract JSON from response (handle markdown code blocks)
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        parsed = json.loads(raw_text)
        latency = int((time.monotonic() - start) * 1000)

        result = TriageResult(
            action=parsed.get("action", "ESCALATE"),
            scene=parsed.get("scene") or None,
            confidence=float(parsed.get("confidence", 0.0)),
            extracted=parsed.get("extracted", {}),
            reason=parsed.get("reason", ""),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency,
        )

        # Force escalation on low confidence (unless resolved)
        if result.confidence < settings.classifier_confidence_threshold and result.action != "RESOLVED":
            result.action = "ESCALATE"
            result.reason += f" (confidence {result.confidence} < {settings.classifier_confidence_threshold})"

        logger.info("Triage: '%s' -> %s scene=%s (conf=%.2f)", message[:50], result.action, result.scene, result.confidence)
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Triage returned invalid JSON: {e}")
        return TriageResult(
            action="ESCALATE",
            scene=None,
            confidence=0.0,
            reason=f"Parse error: {e}",
            latency_ms=int((time.monotonic() - start) * 1000),
        )
    except anthropic.APIError as e:
        logger.error(f"Triage API error: {e}")
        return TriageResult(
            action="ESCALATE",
            scene=None,
            confidence=0.0,
            reason=f"API error: {e}",
            latency_ms=int((time.monotonic() - start) * 1000),
        )
