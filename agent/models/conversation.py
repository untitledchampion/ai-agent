"""Conversation models — tracking dialogue state and history."""

from __future__ import annotations

import json
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Conversation(Base):
    """Active conversation state (replaces Redis for MVP)."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    messenger_type: Mapped[str] = mapped_column(String(50), default="test")

    current_scene: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    scene_data_json: Mapped[str] = mapped_column(Text, default="{}")

    client_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_info_json: Mapped[str] = mapped_column(Text, default="{}")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation",
        order_by="ConversationMessage.created_at",
        cascade="all, delete-orphan",
    )

    @property
    def scene_data(self) -> dict:
        return json.loads(self.scene_data_json)

    @scene_data.setter
    def scene_data(self, value: dict) -> None:
        self.scene_data_json = json.dumps(value, ensure_ascii=False)

    @property
    def client_info(self) -> dict:
        return json.loads(self.client_info_json)

    @client_info.setter
    def client_info(self, value: dict) -> None:
        self.client_info_json = json.dumps(value, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "messenger_type": self.messenger_type,
            "current_scene": self.current_scene,
            "scene_data": self.scene_data,
            "client_name": self.client_name,
            "messages": [m.to_dict() for m in self.messages],
        }


class ConversationMessage(Base):
    """Single message in a conversation."""

    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(20))  # "client" or "agent"
    text: Mapped[str] = mapped_column(Text)

    # Debug info
    scene_slug: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    tools_called_json: Mapped[str] = mapped_column(Text, default="[]")
    debug_json: Mapped[str] = mapped_column(Text, default="{}")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    @property
    def tools_called(self) -> list:
        return json.loads(self.tools_called_json)

    @property
    def debug_info(self) -> dict:
        return json.loads(self.debug_json)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "text": self.text,
            "scene_slug": self.scene_slug,
            "confidence": self.confidence,
            "tools_called": self.tools_called,
            "debug": self.debug_info,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
