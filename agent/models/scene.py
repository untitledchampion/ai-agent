"""Scene model — configurable dialogue scenarios (сценарии)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Scene(Base):
    """Сценарий диалога, который агент умеет обрабатывать.

    Хранит полный конфиг сценария как JSON:
    - trigger: описание, примеры сообщений
    - fields: данные для сбора у клиента
    - tools: какие инструменты вызывать и когда
    - response_template: инструкции для генерации ответа
    - escalate_when: условия для передачи менеджеру
    """

    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    auto_reply: Mapped[bool] = mapped_column(Boolean, default=True)

    # JSON configs
    trigger_json: Mapped[str] = mapped_column(Text, default="{}")
    fields_json: Mapped[str] = mapped_column(Text, default="[]")
    tools_json: Mapped[str] = mapped_column(Text, default="[]")
    response_template: Mapped[str] = mapped_column(Text, default="")
    escalate_when_json: Mapped[str] = mapped_column(Text, default="[]")
    knowledge_json: Mapped[str] = mapped_column(Text, default="[]")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Convenience properties ──

    @property
    def trigger(self) -> dict:
        return json.loads(self.trigger_json)

    @trigger.setter
    def trigger(self, value: dict) -> None:
        self.trigger_json = json.dumps(value, ensure_ascii=False)

    @property
    def fields(self) -> list[dict]:
        return json.loads(self.fields_json)

    @fields.setter
    def fields(self, value: list[dict]) -> None:
        self.fields_json = json.dumps(value, ensure_ascii=False)

    @property
    def tools(self) -> list[dict]:
        return json.loads(self.tools_json)

    @tools.setter
    def tools(self, value: list[dict]) -> None:
        self.tools_json = json.dumps(value, ensure_ascii=False)

    @property
    def escalate_when(self) -> list[str]:
        return json.loads(self.escalate_when_json)

    @escalate_when.setter
    def escalate_when(self, value: list[str]) -> None:
        self.escalate_when_json = json.dumps(value, ensure_ascii=False)

    @property
    def knowledge(self) -> list[dict]:
        return json.loads(self.knowledge_json)

    @knowledge.setter
    def knowledge(self, value: list[dict]) -> None:
        self.knowledge_json = json.dumps(value, ensure_ascii=False)

    def to_dict(self) -> dict:
        """Full scene config as dict (for API responses and LLM prompts)."""
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "active": self.active,
            "sort_order": self.sort_order,
            "auto_reply": self.auto_reply,
            "trigger": self.trigger,
            "fields": self.fields,
            "tools": self.tools,
            "response_template": self.response_template,
            "escalate_when": self.escalate_when,
            "knowledge": self.knowledge,
        }
