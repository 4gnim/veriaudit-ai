from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "VeriAudit AI"
    app_env: str = "development"

    # LLM Keys & Active Models
    gemini_api_key: str
    groq_api_key: str
    gemini_vision_models: list[str] = [
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
    ]
    groq_primary_model: str = "openai/gpt-oss-120b"
    groq_secondary_model: str = "qwen/qwen3.8-27b"

    # Qdrant Cloud
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection_name: str = "veriaudit_policies"

    # Langfuse Observability
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Guardrails
    max_upload_size_mb: int = 5
    rate_limit_per_minute: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
