from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Browser
    browser_headless: bool = False
    use_virtual_display: bool = True
    virtual_display_size: tuple[int, int] = (1920, 1080)
    cdp_port: int = 9222  # Chrome's internal CDP port
    cdp_public_host: str = "127.0.0.1"  # Host in CDP URLs (for Docker: localhost)
    cdp_public_port: int = 9222  # Port in CDP URLs (for Docker: 9223 via socat)

    # Persistent contexts storage
    persistent_contexts_path: str = "./data/contexts"

    # Pool limits
    max_contexts: int = 10

    # Rate limiting
    default_domain_delay_ms: int = 1000  # 1 second between same-domain requests

    # Queue
    max_queue_wait_seconds: int = 300  # 5 minutes

    # Health & eviction
    max_consecutive_errors: int = 5  # Recreate context after this many
    eviction_idle_weight: float = 1.0
    eviction_error_weight: float = 2.0
    eviction_age_weight: float = 0.5

    # Logging
    log_level: str = "INFO"


settings = Settings()
