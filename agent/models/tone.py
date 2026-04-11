"""Tone configuration model — how the agent speaks."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ToneConfig(Base):
    """Agent tone/voice settings. Only one active config at a time.

    Stores persona, style parameters, rules, examples, forbidden phrases.
    """

    __tablename__ = "tone_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), default="default")
    persona: Mapped[str] = mapped_column(
        Text, default="Менеджер отдела продаж компании ОптСилинг"
    )

    # Style parameters as JSON
    parameters_json: Mapped[str] = mapped_column(
        Text,
        default='{"formality": 2, "brevity": 4, "emoji": false, "address": "ты/вы по контексту", "signature": false}',
    )

    # Rules, examples, forbidden phrases as JSON arrays
    rules_json: Mapped[str] = mapped_column(Text, default="[]")
    examples_json: Mapped[str] = mapped_column(Text, default="[]")
    forbidden_phrases_json: Mapped[str] = mapped_column(Text, default="[]")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def parameters(self) -> dict:
        return json.loads(self.parameters_json)

    @parameters.setter
    def parameters(self, value: dict) -> None:
        self.parameters_json = json.dumps(value, ensure_ascii=False)

    @property
    def rules(self) -> list[str]:
        return json.loads(self.rules_json)

    @rules.setter
    def rules(self, value: list[str]) -> None:
        self.rules_json = json.dumps(value, ensure_ascii=False)

    @property
    def examples(self) -> list[dict]:
        return json.loads(self.examples_json)

    @examples.setter
    def examples(self, value: list[dict]) -> None:
        self.examples_json = json.dumps(value, ensure_ascii=False)

    @property
    def forbidden_phrases(self) -> list[str]:
        return json.loads(self.forbidden_phrases_json)

    @forbidden_phrases.setter
    def forbidden_phrases(self, value: list[str]) -> None:
        self.forbidden_phrases_json = json.dumps(value, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "persona": self.persona,
            "parameters": self.parameters,
            "rules": self.rules,
            "examples": self.examples,
            "forbidden_phrases": self.forbidden_phrases,
        }

    def to_prompt_block(self) -> str:
        """Format tone config as a block for the LLM system prompt."""
        params = self.parameters
        lines = [
            f"Ты: {self.persona}",
            "",
            "Стиль:",
            f"- Формальность: {params.get('formality', 3)}/5",
            f"- Краткость: {params.get('brevity', 4)}/5",
            f"- Эмодзи: {'да' if params.get('emoji') else 'нет'}",
            f"- Обращение: {params.get('address', 'на вы')}",
        ]

        if self.rules:
            lines.append("")
            lines.append("Правила:")
            for rule in self.rules:
                lines.append(f"- {rule}")

        if self.forbidden_phrases:
            lines.append("")
            lines.append("ЗАПРЕЩЕНО говорить:")
            for phrase in self.forbidden_phrases:
                lines.append(f"- \"{phrase}\"")

        if self.examples:
            lines.append("")
            lines.append("Примеры эталонных ответов:")
            for ex in self.examples:
                lines.append(f"Клиент: {ex.get('client', '')}")
                lines.append(f"Ответ: {ex.get('agent', '')}")
                lines.append("")

        return "\n".join(lines)
