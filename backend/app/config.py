from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Make the project .env take precedence over ambient OS environment
        # variables, so a stray system-wide DATABASE_URL (e.g. another project's
        # jdbc:... string) never leaks into Secure Chat.
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)

    app_name: str = "Secure Chat"
    debug: bool = True

    database_url: str = "postgresql+asyncpg://securechat:securechat@localhost:5433/securechat"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_exp_minutes: int = 60

    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_audience: str = ""
    dev_auth_bypass: bool = True

    vault_ttl_seconds: int = 3600
    vault_encryption_key: str = "dev-vault-key-32bytes-change-me!!"

    llm_provider: str = "mock"  # mock | bedrock | ollama | openai | auto | vertex
    llm_request_timeout: float = 120.0

    # Auto mode: candidate backends (in priority order) and selection strategy.
    llm_auto_providers: str = "ollama,openai,bedrock"
    llm_auto_strategy: str = "failover"  # failover | round_robin | random

    bedrock_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-opus-20240229-v1:0"
    vertex_project: str = ""
    vertex_location: str = "us-central1"
    vertex_model: str = "claude-3-opus@20240229"

    # Ollama (local or remote) — native /api/chat endpoint
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # Generic OpenAI-compatible endpoint (Groq, OpenRouter, Together, vLLM, LM Studio, ...)
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    max_attachment_bytes: int = 10 * 1024 * 1024
    max_attachments: int = 5
    ocr_timeout_seconds: int = 30

    daily_message_quota: int = 100
    security_profile: str = "pii-redact"


settings = Settings()
