from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    chatapp_email: str
    chatapp_password: str
    chatapp_app_id: str
    chatapp_base_url: str = "https://api.chatapp.online"
    database_url: str = "sqlite+aiosqlite:///./chatapp_data.db"
    rate_limit_per_sec: int = 40  # conservative, API allows 50

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
