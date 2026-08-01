"""
Centralized application config, loaded from environment variables.
Never hardcode secrets -- everything here comes from .env locally, or
real environment variables in Railway for deployed environments.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # Database (Supabase Postgres, direct connection -- SQLAlchemy async)
    DATABASE_URL: str  # e.g. postgresql+asyncpg://postgres:<password>@db.<ref>.supabase.co:5432/postgres

    # Supabase (for anything not going through raw SQLAlchemy, e.g. Storage/Auth)
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # Vapi
    VAPI_SHARED_SECRET: str  # shared secret Vapi sends on every tool call; see app/core/security.py
    VAPI_API_KEY: str = ""   # for calling Vapi's own API (assistant updates, etc.)

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""

    # Anthropic (if the backend itself calls Claude directly, outside of Vapi's own model config)
    ANTHROPIC_API_KEY: str = ""


settings = Settings()
