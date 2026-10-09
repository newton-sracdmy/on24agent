"""Application configuration management using Pydantic Settings v2.

Loads environment variables with validation, type coercion, and defaults.
"""

from typing import List, Literal, Optional
from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # General Environment
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    APP_NAME: str = "gabster-ai"
    DEBUG: bool = False
    SECRET_KEY: str = Field(
        default="09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7",
        min_length=32,
    )
    API_V1_STR: str = "/api/v1"
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    ALLOWED_HOSTS: List[str] = ["*"]
    CORS_ORIGINS: List[str] = ["*"]

    # Database Configuration (PostgreSQL 16 + pgvector)
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "gabster_ai"
    POSTGRES_USER: str = "gabster_app"
    POSTGRES_PASSWORD: str = "secure_app_password"
    POSTGRES_ADMIN_USER: str = "postgres"
    POSTGRES_ADMIN_PASSWORD: str = "secure_postgres_password"
    DATABASE_URL: Optional[str] = None
    DATABASE_ADMIN_URL: Optional[str] = None
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], info) -> str:
        if isinstance(v, str) and v:
            return v
        data = info.data
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=data.get("POSTGRES_USER", "gabster_app"),
                password=data.get("POSTGRES_PASSWORD", "secure_app_password"),
                host=data.get("POSTGRES_SERVER", "localhost"),
                port=data.get("POSTGRES_PORT", 5432),
                path=data.get("POSTGRES_DB", "gabster_ai"),
            )
        )

    @field_validator("DATABASE_ADMIN_URL", mode="before")
    @classmethod
    def assemble_admin_db_connection(cls, v: Optional[str], info) -> str:
        if isinstance(v, str) and v:
            return v
        data = info.data
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=data.get("POSTGRES_ADMIN_USER", "postgres"),
                password=data.get("POSTGRES_ADMIN_PASSWORD", "secure_postgres_password"),
                host=data.get("POSTGRES_SERVER", "localhost"),
                port=data.get("POSTGRES_PORT", 5432),
                path=data.get("POSTGRES_DB", "gabster_ai"),
            )
        )

    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0
    REDIS_URL: Optional[str] = None
    REDIS_CACHE_TTL_SECONDS: int = 3600

    @field_validator("REDIS_URL", mode="before")
    @classmethod
    def assemble_redis_connection(cls, v: Optional[str], info) -> str:
        if isinstance(v, str) and v:
            return v
        data = info.data
        host = data.get("REDIS_HOST", "localhost")
        port = data.get("REDIS_PORT", 6379)
        password = data.get("REDIS_PASSWORD")
        db = data.get("REDIS_DB", 0)
        auth = f":{password}@" if password else ""
        return f"redis://{auth}{host}:{port}/{db}"

    # Celery Configuration
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    CELERY_TASK_ALWAYS_EAGER: bool = False

    @field_validator("CELERY_BROKER_URL", mode="before")
    @classmethod
    def assemble_celery_broker(cls, v: Optional[str], info) -> str:
        if isinstance(v, str) and v:
            return v
        data = info.data
        host = data.get("REDIS_HOST", "localhost")
        port = data.get("REDIS_PORT", 6379)
        password = data.get("REDIS_PASSWORD")
        auth = f":{password}@" if password else ""
        return f"redis://{auth}{host}:{port}/1"

    @field_validator("CELERY_RESULT_BACKEND", mode="before")
    @classmethod
    def assemble_celery_backend(cls, v: Optional[str], info) -> str:
        if isinstance(v, str) and v:
            return v
        data = info.data
        host = data.get("REDIS_HOST", "localhost")
        port = data.get("REDIS_PORT", 6379)
        password = data.get("REDIS_PASSWORD")
        auth = f":{password}@" if password else ""
        return f"redis://{auth}{host}:{port}/2"

    # Security & JWT Tokens
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    INVITATION_EXPIRE_HOURS: int = 72
    SESSION_IDLE_TIMEOUT_MINUTES: int = 120
    JWT_ALGORITHM: str = "HS256"
    ENCRYPTION_KEY: str = Field(
        default="cE1xQzZWM1drR3VwOHdZZjBXZk9lcmx0aWlCdmJ0bVE=",  # 32-byte url-safe base64 default for dev
        description="Fernet symmetric key for encrypting API tokens and credentials at rest",
    )
    BCRYPT_ROUNDS: int = 12

    # Media & File Storage
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    STORAGE_LOCAL_ROOT: str = "./storage_uploads"
    S3_BUCKET_NAME: Optional[str] = "gabster-media-uploads"
    S3_REGION: Optional[str] = "us-east-1"
    S3_ACCESS_KEY_ID: Optional[str] = None
    S3_SECRET_ACCESS_KEY: Optional[str] = None
    S3_ENDPOINT_URL: Optional[str] = None

    # External Provider Credentials
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    VOICE_API_KEY: Optional[str] = None

    # Channels
    META_WHATSAPP_API_TOKEN: Optional[str] = None
    META_WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    META_WHATSAPP_WABA_ID: Optional[str] = None
    META_WEBHOOK_VERIFY_TOKEN: str = "gabster_meta_verify_token_secure_string"
    FB_PAGE_ID: Optional[str] = None
    FB_PAGE_ACCESS_TOKEN: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_WEBHOOK_SECRET: Optional[str] = None

    # Billing & Stripe
    STRIPE_API_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None

    # Observability
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    ENABLE_METRICS: bool = True
    METRICS_PORT: int = 9090
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None
    OTEL_SERVICE_NAME: str = "gabster-ai-backend"


settings = Settings()
