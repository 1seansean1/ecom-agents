"""Holly Grace backend configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Environment-driven settings for the Holly Grace backend."""

    agents_url: str = "http://localhost:8050"
    agents_token: str = ""
    langsmith_api_key: str = ""
    langsmith_project: str = "holly-grace"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Provider admin keys for real billing data (optional)
    anthropic_admin_key: str = ""
    openai_admin_key: str = ""

    # Console authentication
    console_user_email: str = "sean.p.allen9@gmail.com"
    console_user_password: str = "admin"
    console_jwt_secret: str = "CHANGE_ME_IN_PRODUCTION_64_CHAR_SECRET"

    model_config = {"env_prefix": "HOLLY_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
