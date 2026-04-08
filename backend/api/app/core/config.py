from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Hospital Booking API"
    api_v1_prefix: str = "/api/v1"
    database_url: str
    secret_key: str
    access_token_expire_minutes: int = 120
    # Shared secret for voice agent → API (header X-Agent-Key). If unset, agent routes return 503.
    agent_api_key: str | None = None


settings = Settings()
