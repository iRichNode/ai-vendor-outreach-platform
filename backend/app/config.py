"""Application configuration.

All configuration comes from environment variables (see .env.example).
Secrets are never hard-coded here.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Core ---
    APP_NAME: str = "AI Vendor Outreach Platform"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DEBUG: bool = False
    API_PREFIX: str = "/api"
    SECRET_KEY: str = Field(default="change-me-in-production")
    # Comma separated list of allowed CORS origins
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8080"
    # Base URL used to build absolute links (Gmail OAuth redirect, push notification URL)
    BASE_URL: str = "http://localhost:8000"
    DEMO_MODE: bool = False

    # --- Database / queue ---
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/outreach"
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Initial admin (first-run setup) ---
    INITIAL_ADMIN_USERNAME: str = ""
    INITIAL_ADMIN_PASSWORD: str = ""
    INITIAL_ADMIN_EMAIL: str = ""

    # --- AI (OpenRouter / any OpenAI-compatible endpoint) ---
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_MODEL: str = "openai/gpt-4o-mini"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 900

    # --- Gmail ---
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""
    GMAIL_WATCH_EXPIRY_HOURS: int = 168  # Gmail push notifications TTL is 7 days
    GMAIL_TRANSPORT: str = "auto"  # auto | smtp | api | fake
    GMAIL_SENDER_EMAIL: str = ""
    GMAIL_SENDER_NAME: str = ""
    GMAIL_TOKEN_JSON: str = ""  # OAuth token JSON (dev convenience)
    GMAIL_TOKEN_FILE: str = ""   # path to token.json (persistent OAuth)
    GMAIL_PLAIN_TEXT: bool = False

    # --- Vendor discovery ---
    DISCOVERY_PROVIDER: str = "demo"
    DISCOVERY_API_URL: str = ""
    DISCOVERY_API_KEY: str = ""

    # --- Vendor research ---
    RESEARCH_USER_AGENT: str = ""
    RESEARCH_TIMEOUT_SECONDS: float = 20.0
    RESEARCH_POLITENESS_SECONDS: float = 1.0

    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # --- Security ---
    SESSION_COOKIE_NAME: str = "adv_session"
    SESSION_EXPIRE_MINUTES: int = 60 * 24 * 7
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: str = "lax"
    AUTH_RATE_LIMIT: str = "10/minute"
    PASSWORD_ITERATIONS: int = 600_000

    # --- Sending defaults (overridable per campaign) ---
    SEND_BATCH_SIZE: int = 1
    SEND_MIN_DELAY_MINUTES: int = 5
    SEND_MAX_DELAY_MINUTES: int = 12
    DAILY_MAX_EMAILS: int = 30
    SENDING_START_HOUR: int = 9
    SENDING_END_HOUR: int = 17
    SENDING_DAYS: str = "1,2,3,4,5"  # ISO weekday numbers, 1=Monday
    CAMPAIGN_TIMEZONE: str = "America/New_York"

    # --- AI reply delay ---
    AI_REPLY_MODE: Literal["immediate", "delayed"] = "delayed"
    AI_REPLY_MIN_DELAY_MINUTES: int = 3
    AI_REPLY_MAX_DELAY_MINUTES: int = 10

    # --- Worker ---
    CELERY_TASK_MAX_RETRIES: int = 5
    JOB_STALE_AFTER_SECONDS: int = 300
    DISPATCH_INTERVAL_SECONDS: int = 60

    # --- Scheduler maintenance ---
    SCHEDULER_INTERVAL_SECONDS: int = 300
    JOB_RETENTION_DAYS: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def sending_days_set(self) -> set[int]:
        try:
            return {int(d) for d in self.SENDING_DAYS.split(",") if d.strip()}
        except ValueError:
            return {1, 2, 3, 4, 5}


@lru_cache
def get_settings() -> Settings:
    return Settings()