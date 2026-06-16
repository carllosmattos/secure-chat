from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Secure Chat"
    debug: bool = True

    database_url: str = "postgresql+asyncpg://securechat:securechat@localhost:5432/securechat"
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

    llm_provider: str = "mock"  # mock | bedrock | vertex
    bedrock_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-opus-20240229-v1:0"
    vertex_project: str = ""
    vertex_location: str = "us-central1"
    vertex_model: str = "claude-3-opus@20240229"

    max_attachment_bytes: int = 10 * 1024 * 1024
    max_attachments: int = 5
    ocr_timeout_seconds: int = 30

    daily_message_quota: int = 100
    security_profile: str = "pii-redact"


settings = Settings()
