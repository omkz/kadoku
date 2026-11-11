from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "sqlite:///./kadoku-dev.db"  # local-only fallback
    cors_origins: str = "http://localhost:3000"
    frontend_url: str = "http://localhost:3000"
    better_auth_url: str = "http://localhost:3000"
    admin_user_ids: str = ""  # comma-separated Better Auth user IDs (JWT sub), fail closed by default
    guest_quota_secret: str = ""  # required for quota when exposed publicly
    guest_recommendations_daily: int = 1
    member_recommendations_daily: int = 5
    ai_model: str = ""  # e.g. openai/gpt-5-mini, gemini/gemini-2.5-flash
    ai_timeout_seconds: float = Field(default=12, gt=0, le=30)
    ai_max_output_tokens: int = Field(default=240, ge=80, le=512)
    studio_agent_enabled: bool = False  # explicit opt-in for admin AI actions
    studio_agent_model: str = ""  # fallback to AI_MODEL when unset; Gemini via LiteLLM
    # Declare provider credentials so pydantic-settings loads them from apps/api/.env.
    # Values are passed to LiteLLM explicitly; BaseSettings does not export .env
    # variables into os.environ for the SDK to discover automatically.
    gemini_api_key: str = Field(default="", repr=False)
    google_api_key: str = Field(default="", repr=False)
    openai_api_key: str = Field(default="", repr=False)
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
