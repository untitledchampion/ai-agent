"""Agent configuration — all settings from environment."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


def _load_dotenv_key(key: str, env_file: str = ".env") -> str:
    """Manually read a key from .env file, bypassing env var interference."""
    env_path = Path(env_file)
    if not env_path.exists():
        # Try relative to this file's parent
        env_path = Path(__file__).parent.parent / env_file
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip()
    return os.environ.get(key, "")


class Settings(BaseSettings):
    # ChatApp credentials (for future webhook integration)
    chatapp_email: str = ""
    chatapp_password: str = ""
    chatapp_app_id: str = ""
    chatapp_base_url: str = "https://api.chatapp.online"

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/agent.db"
    collector_db_url: str = "sqlite+aiosqlite:///./data/chatapp_data.db"

    # LLM
    anthropic_api_key: str = ""
    classifier_model: str = "claude-haiku-4-5-20251001"
    responder_model: str = "claude-haiku-4-5-20251001"

    # Agent
    classifier_confidence_threshold: float = 0.7
    max_history_messages: int = 10
    state_ttl_hours: int = 24

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

# Fix: env var ANTHROPIC_API_KEY="" from parent shell overrides .env file value.
# Read directly from .env if pydantic got an empty string.
if not settings.anthropic_api_key:
    _key = _load_dotenv_key("ANTHROPIC_API_KEY")
    if _key:
        object.__setattr__(settings, "anthropic_api_key", _key)
