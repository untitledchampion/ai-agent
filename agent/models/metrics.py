"""Metrics model — tracking agent performance."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AgentMetric(Base):
    """Single agent interaction metric for analytics."""

    __tablename__ = "agent_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String(255), index=True)
    scene_slug: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    action: Mapped[str] = mapped_column(String(50))  # "auto_reply", "escalation", "tool_call", "error"
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # LLM cost tracking
    classifier_tokens: Mapped[int] = mapped_column(Integer, default=0)
    responder_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    # Timing
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    details: Mapped[str] = mapped_column(Text, default="{}")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "scene_slug": self.scene_slug,
            "action": self.action,
            "confidence": self.confidence,
            "classifier_tokens": self.classifier_tokens,
            "responder_tokens": self.responder_tokens,
            "total_cost_usd": self.total_cost_usd,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
