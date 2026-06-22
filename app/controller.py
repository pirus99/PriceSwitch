"""Core control engine.

Runs the background polling loop, evaluates the switch logic and drives the
GPIO outputs. Exposes the live runtime state for the dashboard.

Switch logic (AUTO mode):
  * price <= switch_price                     -> LOW output ON
  * price >  switch_price + threshold         -> HIGH output ON
  * in between (the band)                      -> keep current output
A hysteresis *time* lockout prevents a new switch event from happening until
``hysteresis_seconds`` have passed since the last switch.

MANUAL mode ignores the price and follows ``manual_output``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from .database import EventLog
from .gpio import GpioController, OutputName
from .providers import PriceResult, ProviderError, fetch_price
from .settings import Settings, SettingsStore

logger = logging.getLogger(__name__)

RETENTION_INTERVAL = 3600  # run retention cleanup at most hourly


@dataclass(slots=True)
class RuntimeState:
    """Snapshot of the live state shown on the dashboard."""

    output: OutputName = "NONE"
    mode: str = "AUTO"
    price: float | None = None
    currency: str = "EUR"
    unit: str = "c/kWh"
    price_timestamp: str | None = None
    price_age_seconds: int | None = None
    last_poll: str | None = None
    last_switch: str | None = None
    provider: str = ""
    zone: str = ""
    stale: bool = False
    fallback: bool = False
    simulated: bool = False
    error: str | None = None
    locked_until: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class SwitchController:
    """Owns the polling loop and the switch decision logic."""

    def __init__(
        self,
        store: SettingsStore,
        gpio: GpioController,
        event_log: EventLog,
    ) -> None:
        self._store = store
        self._gpio = gpio
        self._log = event_log
        self._state = RuntimeState()
        self._lock = asyncio.Lock()
        self._wakeup = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._last_switch_monotonic: float | None = None
        self._last_retention = 0.0
        self._running = False

        settings = store.current
        self._gpio.configure(settings.gpio_high, settings.gpio_low)
        self._state.simulated = self._gpio.simulated
        self._state.mode = settings.mode
        self._state.provider = settings.provider
        self._state.zone = settings.zone

    # -- lifecycle ----------------------------------------------------------
    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run(), name="poll-loop")
        logger.info("SwitchController started")

    async def stop(self) -> None:
        self._running = False
        self._wakeup.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._gpio.shutdown()
        logger.info("SwitchController stopped")

    def request_refresh(self) -> None:
        """Wake the poll loop immediately (e.g. after a settings change)."""
        self._wakeup.set()

    # -- public state -------------------------------------------------------
    def snapshot(self) -> RuntimeState:
        return self._state

    # -- main loop ----------------------------------------------------------
    async def _run(self) -> None:
        while self._running:
            settings = self._store.current
            try:
                await self._tick(settings)
            except Exception:  # noqa: BLE001 - loop must never die
                logger.exception("Unhandled error in poll loop")
            await self._maybe_retention(settings)

            interval = settings.poll_interval
            try:
                await asyncio.wait_for(self._wakeup.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
            finally:
                self._wakeup.clear()

    async def _tick(self, settings: Settings) -> None:
        """One control cycle: keep GPIO config current, fetch, decide."""
        self._gpio.configure(settings.gpio_high, settings.gpio_low)
        self._state.mode = settings.mode
        self._state.provider = settings.provider
        self._state.zone = settings.zone
        self._state.simulated = self._gpio.simulated

        if settings.mode == "MANUAL":
            await self._apply_manual(settings)
            return

        await self._apply_auto(settings)

    async def _apply_manual(self, settings: Settings) -> None:
        target: OutputName = settings.manual_output
        # Still refresh the price for display purposes, but ignore failures.
        try:
            result = await fetch_price(settings.provider, settings.zone)
            self._record_price(result)
            self._state.error = None
        except ProviderError as exc:
            self._state.error = str(exc)
        await self._switch(target, self._state.price, "MANUAL", "manual selection")

    async def _apply_auto(self, settings: Settings) -> None:
        try:
            result = await fetch_price(settings.provider, settings.zone)
        except ProviderError as exc:
            self._state.error = str(exc)
            logger.warning("Price fetch failed: %s", exc)
            return

        self._record_price(result)
        self._state.error = None

        price = result.price
        switch_price = settings.switch_price
        upper = switch_price + settings.threshold

        current = self._gpio.state
        if price <= switch_price:
            target: OutputName = "LOW"
            reason = f"price {price} <= switch {switch_price}"
        elif price > upper:
            target = "HIGH"
            reason = f"price {price} > switch+threshold {upper}"
        else:
            # Inside the deadband: hold current output (default HIGH if none).
            target = current if current != "NONE" else "HIGH"
            reason = f"price {price} within band, hold {target}"

        await self._switch(target, price, "AUTO", reason)

    # -- switching with hysteresis -----------------------------------------
    async def _switch(
        self,
        target: OutputName,
        price: float | None,
        mode: str,
        reason: str,
    ) -> None:
        async with self._lock:
            current = self._gpio.state
            if target == current:
                return

            settings = self._store.current
            now = asyncio.get_event_loop().time()
            if (
                mode == "AUTO"
                and self._last_switch_monotonic is not None
                and settings.hysteresis_seconds > 0
            ):
                elapsed = now - self._last_switch_monotonic
                remaining = settings.hysteresis_seconds - elapsed
                if remaining > 0:
                    self._state.locked_until = self._iso_in(remaining)
                    logger.debug(
                        "Switch to %s suppressed by hysteresis (%.0fs left)",
                        target,
                        remaining,
                    )
                    return

            new_state = self._gpio.set_output(target)
            self._last_switch_monotonic = now
            self._state.output = new_state
            self._state.last_switch = datetime.now(timezone.utc).isoformat()
            self._state.locked_until = None
            self._log.add_event(new_state, price, mode, reason)

    # -- helpers ------------------------------------------------------------
    def _record_price(self, result: PriceResult) -> None:
        self._state.price = result.price
        self._state.currency = result.currency
        self._state.unit = result.unit
        self._state.price_timestamp = result.timestamp.isoformat()
        self._state.price_age_seconds = result.age_seconds
        self._state.last_poll = datetime.now(timezone.utc).isoformat()
        self._state.stale = result.stale
        self._state.fallback = result.fallback

    async def _maybe_retention(self, settings: Settings) -> None:
        now = asyncio.get_event_loop().time()
        if now - self._last_retention < RETENTION_INTERVAL:
            return
        self._last_retention = now
        days = settings.retention_days()
        await asyncio.to_thread(self._log.purge_older_than, days)

    @staticmethod
    def _iso_in(seconds: float) -> str:
        from datetime import timedelta

        return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
