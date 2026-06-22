"""GPIO output control with an automatic mock fallback.

On a Raspberry Pi this drives two relay outputs via gpiozero.
Off-Pi (e.g. development on Windows) it transparently falls back to an
in-memory mock so the rest of the application behaves identically.

A hard safety invariant is enforced here: the HIGH and LOW outputs can
never be energised at the same time.
"""

from __future__ import annotations

import logging
import threading
from typing import Literal

from .env_config import env_config

logger = logging.getLogger(__name__)

OutputName = Literal["HIGH", "LOW", "NONE"]

try:  # pragma: no cover - hardware dependent
    from gpiozero import OutputDevice

    _GPIO_AVAILABLE = True
except Exception:  # noqa: BLE001 - any import issue means no real GPIO
    OutputDevice = None  # type: ignore[assignment]
    _GPIO_AVAILABLE = False


class _MockOutput:
    """Minimal stand-in for gpiozero.OutputDevice used off-Pi."""

    def __init__(self, pin: int, active_high: bool, initial_value: bool) -> None:
        self.pin = pin
        self.active_high = active_high
        self.value = 1 if initial_value else 0

    def on(self) -> None:
        self.value = 1

    def off(self) -> None:
        self.value = 0

    def close(self) -> None:
        self.value = 0


class GpioController:
    """Owns the two relay outputs and guarantees they are mutually exclusive."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active_low = env_config.gpio_active_low
        self._high_pin: int | None = None
        self._low_pin: int | None = None
        self._high_dev = None
        self._low_dev = None
        self._state: OutputName = "NONE"
        self.simulated = not _GPIO_AVAILABLE
        if self.simulated:
            logger.warning("gpiozero unavailable - running in GPIO SIMULATION mode")

    # -- device lifecycle ---------------------------------------------------
    def configure(self, high_pin: int, low_pin: int) -> None:
        """(Re)create output devices for the configured pins."""
        with self._lock:
            if high_pin == self._high_pin and low_pin == self._low_pin and self._high_dev:
                return
            self._close_devices()
            self._high_pin = high_pin
            self._low_pin = low_pin
            self._high_dev = self._make_device(high_pin)
            self._low_dev = self._make_device(low_pin)
            self._state = "NONE"
            self._apply()
            logger.info(
                "GPIO configured: HIGH=pin%s LOW=pin%s active_low=%s simulated=%s",
                high_pin,
                low_pin,
                self._active_low,
                self.simulated,
            )

    def _make_device(self, pin: int):
        active_high = not self._active_low
        if _GPIO_AVAILABLE:  # pragma: no cover - hardware dependent
            return OutputDevice(pin, active_high=active_high, initial_value=False)
        return _MockOutput(pin, active_high=active_high, initial_value=False)

    def _close_devices(self) -> None:
        for dev in (self._high_dev, self._low_dev):
            if dev is not None:
                try:
                    dev.close()
                except Exception:  # noqa: BLE001
                    pass
        self._high_dev = self._low_dev = None

    # -- switching ----------------------------------------------------------
    def set_output(self, target: OutputName) -> OutputName:
        """Energise exactly one (or no) output. Returns the new state."""
        with self._lock:
            self._state = target
            self._apply()
            return self._state

    def _apply(self) -> None:
        """Drive devices to match ``self._state`` (mutually exclusive)."""
        if self._high_dev is None or self._low_dev is None:
            return
        # Always switch the to-be-off output off first for safety.
        if self._state == "HIGH":
            self._low_dev.off()
            self._high_dev.on()
        elif self._state == "LOW":
            self._high_dev.off()
            self._low_dev.on()
        else:
            self._high_dev.off()
            self._low_dev.off()

    @property
    def state(self) -> OutputName:
        with self._lock:
            return self._state

    def shutdown(self) -> None:
        with self._lock:
            self.set_output("NONE")
            self._close_devices()


gpio_controller = GpioController()
