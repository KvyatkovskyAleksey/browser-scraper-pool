from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost/"

    # Browser Pool
    browser_pool_size: int = 3

    # Logging
    log_level: str = "INFO"

    # Persistent contexts storage
    persistent_contexts_path: str = "./data/contexts"


settings = Settings()
