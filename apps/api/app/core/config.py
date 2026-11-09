from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "sqlite:///./kadoku-dev.db"  # local-only fallback
    cors_origins: str = "http://localhost:3000"
    frontend_url: str = "http://localhost:3000"
    better_auth_url: str = "http://localhost:3000"
    guest_quota_secret: str = ""  # required for quota when exposed publicly
    guest_recommendations_daily: int = 1
    member_recommendations_daily: int = 5
    ai_model: str = ""  # e.g. openai/gpt-5-mini, gemini/gemini-2.5-flash
    ai_timeout_seconds: int = 12
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_webhook_id: str = ""
    paypal_mode: str = "sandbox"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.environment == "production" and (not settings.guest_quota_secret or len(settings.guest_quota_secret) < 32):
        raise RuntimeError("GUEST_QUOTA_SECRET must be at least 32 characters in production")
    return settings
