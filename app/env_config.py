"""Static application configuration loaded from environment / .env file.

These settings change rarely and are not editable through the web UI.
Frequently-changed settings live in the JSON config (see settings.py).
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvConfig(BaseSettings):
    """Static settings sourced from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Web server
    host: str = "0.0.0.0"
    port: int = 8000

    # Security
    secret_key: str = "change-me-to-a-long-random-string"
    auth_required: bool = False
    auth_password: str = "admin"

    # Files
    config_file: str = "config.json"
    db_file: str = "priceswitch.db"
    log_file: str = "priceswitch.log"
    log_level: str = "INFO"

    # GPIO electrical configuration
    gpio_active_low: bool = True

    # Provider API keys
    tibber_token: str = ""
    entsoe_token: str = ""

    @property
    def base_dir(self) -> Path:
        """Project root directory."""
        return Path(__file__).resolve().parent.parent

    def resolve(self, filename: str) -> Path:
        """Resolve a possibly-relative file path against the project root."""
        path = Path(filename)
        if path.is_absolute():
            return path
        return self.base_dir / path


env_config = EnvConfig()
