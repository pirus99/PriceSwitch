"""Request/response schemas for the JSON API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SettingsUpdate(BaseModel):
    """Partial settings update sent from the Settings page."""

    provider: str | None = None
    zone: str | None = None
    poll_interval: int | None = Field(default=None, ge=10, le=86400)

    switch_price: float | None = None
    threshold: float | None = Field(default=None, ge=0.0)
    hysteresis_seconds: int | None = Field(default=None, ge=0, le=86400)

    gpio_high: int | None = Field(default=None, ge=0, le=27)
    gpio_low: int | None = Field(default=None, ge=0, le=27)

    mode: Literal["AUTO", "MANUAL"] | None = None
    manual_output: Literal["HIGH", "LOW"] | None = None

    retention_value: int | None = Field(default=None, ge=0)
    retention_unit: Literal["weeks", "months"] | None = None

    def to_update_dict(self) -> dict:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class LoginRequest(BaseModel):
    password: str
