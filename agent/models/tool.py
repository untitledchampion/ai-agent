"""Tool model — external API integrations configured via admin panel."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Tool(Base):
    """An external tool (API endpoint) that the agent can call.

    Stores HTTP request config as JSON:
    - request: {method, url, headers, params/body}
    - response_mapping: JSONPath-like extraction rules
    - fallback: message to use if tool fails
    """

    __tablename__ = "tools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # HTTP request config
    request_json: Mapped[str] = mapped_column(Text, default="{}")
    # Response field mapping
    response_mapping_json: Mapped[str] = mapped_column(Text, default="{}")

    fallback_message: Mapped[str] = mapped_column(
        Text, default="Не удалось получить данные. Уточню у менеджера."
    )
    timeout_ms: Mapped[int] = mapped_column(Integer, default=5000)
    retry_count: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def request_config(self) -> dict:
        return json.loads(self.request_json)

    @request_config.setter
    def request_config(self, value: dict) -> None:
        self.request_json = json.dumps(value, ensure_ascii=False)

    @property
    def response_mapping(self) -> dict:
        return json.loads(self.response_mapping_json)

    @response_mapping.setter
    def response_mapping(self, value: dict) -> None:
        self.response_mapping_json = json.dumps(value, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "active": self.active,
            "request": self.request_config,
            "response_mapping": self.response_mapping,
            "fallback_message": self.fallback_message,
            "timeout_ms": self.timeout_ms,
            "retry_count": self.retry_count,
        }
