"""User-editable settings, persisted as JSON and managed via the web UI.

These are the settings the user changes frequently on the Settings page:
zone, poll interval, GPIO pins, threshold, hysteresis, switch price,
operating mode, manual output, provider selection and log retention.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

Mode = Literal["AUTO", "MANUAL"]
ManualOutput = Literal["HIGH", "LOW"]


class Settings(BaseModel):
    """Frequently-changed, web-editable settings."""

    # --- Provider / polling ---
    provider: str = Field(default="elecz", description="Price provider id")
    zone: str = Field(default="DE", description="Bidding zone / market area")
    poll_interval: int = Field(
        default=300, ge=10, le=86400, description="Poll interval in seconds"
    )

    # --- Switch logic ---
    switch_price: float = Field(
        default=10.0, description="Price (c/kWh) at/below which LOW output turns on"
    )
    threshold: float = Field(
        default=2.0,
        ge=0.0,
        description="Offset added to switch price to form the switch-back band",
    )
    hysteresis_seconds: int = Field(
        default=300,
        ge=0,
        le=86400,
        description="Minimum time between switch events (lockout)",
    )

    # --- GPIO pins (BCM numbering) ---
    gpio_high: int = Field(default=23, ge=0, le=27, description="High-price output pin")
    gpio_low: int = Field(default=24, ge=0, le=27, description="Low-price output pin")

    # --- Operating mode ---
    mode: Mode = Field(default="AUTO")
    manual_output: ManualOutput = Field(default="HIGH")

    # --- Log retention ---
    retention_value: int = Field(
        default=3, ge=0, description="Retention amount (0 = keep forever)"
    )
    retention_unit: Literal["weeks", "months"] = Field(default="months")

    @field_validator("zone")
    @classmethod
    def _strip_zone(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("gpio_low")
    @classmethod
    def _pins_differ(cls, v: int, info) -> int:
        gpio_high = info.data.get("gpio_high")
        if gpio_high is not None and v == gpio_high:
            raise ValueError("High and Low output pins must be different")
        return v

    def retention_days(self) -> int | None:
        """Return retention period in days, or None when disabled."""
        if self.retention_value <= 0:
            return None
        if self.retention_unit == "weeks":
            return self.retention_value * 7
        return self.retention_value * 30


class SettingsStore:
    """Thread-safe JSON-backed store for the user settings."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._settings = self._load()

    def _load(self) -> Settings:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                return Settings(**raw)
            except (json.JSONDecodeError, ValueError, OSError) as exc:
                logger.warning("Could not load settings (%s); using defaults", exc)
        settings = Settings()
        self._write(settings)
        return settings

    def _write(self, settings: Settings) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self._path)

    @property
    def current(self) -> Settings:
        with self._lock:
            return self._settings

    def update(self, data: dict) -> Settings:
        """Validate and persist a partial or full settings update."""
        with self._lock:
            merged = self._settings.model_dump()
            merged.update(data)
            new_settings = Settings(**merged)
            self._write(new_settings)
            self._settings = new_settings
            logger.info("Settings updated")
            return new_settings
