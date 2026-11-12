from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    staging_demo_seed_enabled: bool = False  # one-off operator process only; never configure on web service
    database_url: str = "sqlite:///./kadoku-dev.db"  # local-only fallback
    cors_origins: str = "http://localhost:3000"
    frontend_url: str = "http://localhost:3000"
    better_auth_url: str = "http://localhost:3000"
    guest_quota_secret: str = ""  # required for quota when exposed publicly
    guest_recommendations_daily: int = 3
    member_recommendations_daily: int = 5
    ai_model: str = ""  # e.g. openai/gpt-5-mini, gemini/gemini-2.5-flash
    ai_timeout_seconds: float = Field(default=12, gt=0, le=30)
    ai_max_output_tokens: int = Field(default=240, ge=80, le=512)
    studio_agent_enabled: bool = False  # explicit opt-in for admin AI actions
    studio_agent_model: str = ""  # fallback to AI_MODEL when unset; Gemini via LiteLLM
    studio_agent_min_interval_seconds: float = Field(default=0, ge=0, le=60)  # per-process pacing; set 15 for a 5 RPM model
    # Pydantic loads .env keys but does not export them to LiteLLM.
    gemini_api_key: str = Field(default="", repr=False)
    google_api_key: str = Field(default="", repr=False)
    openai_api_key: str = Field(default="", repr=False)
    groq_api_key: str = Field(default="", repr=False)  # AG Studio GroqCloud free-tier or paid key
    nebius_api_key: str = Field(default="", repr=False)  # Token Factory credits / API
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_webhook_id: str = ""
    paypal_mode: str = "sandbox"

    @field_validator("database_url")
    @classmethod
    def normalize_postgres_driver(cls, value: str) -> str:
        """Render provides postgresql://, but Kadoku installs psycopg 3, not psycopg2."""
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix):]
        return value


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.environment == "production" and (not settings.guest_quota_secret or len(settings.guest_quota_secret) < 32):
        raise RuntimeError("GUEST_QUOTA_SECRET must be at least 32 characters in production")
    return settings
