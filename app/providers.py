"""Energy price providers.

Each provider knows how to fetch the *current* spot price for a given zone
and normalise the response into a :class:`PriceResult`.

Providers are ordered by preference:
  1. Free, no API key required
  2. Free, API key required
  3. Paid, API key required
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from .env_config import env_config

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 15.0


@dataclass(slots=True)
class PriceResult:
    """Normalised price reading from any provider."""

    price: float                      # value in c/kWh
    currency: str
    unit: str
    timestamp: datetime               # time the price refers to
    source: str
    zone: str
    stale: bool = False
    fallback: bool = False
    raw: dict = field(default_factory=dict)

    @property
    def age_seconds(self) -> int:
        return max(0, int((datetime.now(timezone.utc) - self.timestamp).total_seconds()))


@dataclass(slots=True)
class ProviderInfo:
    """Static metadata describing a provider for the web UI."""

    id: str
    name: str
    tier: str                         # "free", "free-key", "paid-key"
    requires_key: bool
    zones: list[str]
    zone_hint: str
    homepage: str
    needs_token_env: str | None = None


class ProviderError(RuntimeError):
    """Raised when a provider cannot deliver a price."""


def _to_ct_per_kwh(value_eur_mwh: float) -> float:
    """Convert EUR/MWh to ct/kWh (1 EUR/MWh = 0.1 ct/kWh)."""
    return round(value_eur_mwh / 10.0, 3)


class BaseProvider:
    info: ProviderInfo

    async def fetch(self, zone: str, client: httpx.AsyncClient) -> PriceResult:
        raise NotImplementedError


class EleczProvider(BaseProvider):
    info = ProviderInfo(
        id="elecz",
        name="Elecz.com Spot (ENTSO-E)",
        tier="free",
        requires_key=False,
        zones=["DE", "AT", "FR", "BE", "NL", "CH", "DK1", "DK2", "ES", "IT", "PL"],
        zone_hint="ENTSO-E bidding zone, e.g. DE, AT, FR",
        homepage="https://elecz.com",
    )

    async def fetch(self, zone: str, client: httpx.AsyncClient) -> PriceResult:
        url = "https://elecz.com/signal/spot"
        resp = await client.get(url, params={"zone": zone})
        resp.raise_for_status()
        data = resp.json()
        ts = data.get("timestamp")
        timestamp = (
            datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
        )
        return PriceResult(
            price=float(data["price"]),
            currency=data.get("currency", "EUR"),
            unit=data.get("unit", "c/kWh"),
            timestamp=timestamp,
            source=data.get("source", "Elecz"),
            zone=data.get("zone", zone),
            stale=bool(data.get("stale", False)),
            fallback=bool(data.get("fallback", False)),
            raw=data,
        )


class AwattarProvider(BaseProvider):
    """aWATTar market data (Germany / Austria), free, no key."""

    info = ProviderInfo(
        id="awattar_de",
        name="aWATTar (DE/AT)",
        tier="free",
        requires_key=False,
        zones=["DE", "AT"],
        zone_hint="DE = api.awattar.de, AT = api.awattar.at",
        homepage="https://www.awattar.de",
    )

    async def fetch(self, zone: str, client: httpx.AsyncClient) -> PriceResult:
        domain = "at" if zone.upper() == "AT" else "de"
        url = f"https://api.awattar.{domain}/v1/marketdata"
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        entries = data.get("data", [])
        if not entries:
            raise ProviderError("aWATTar returned no market data")

        now_ms = datetime.now(timezone.utc).timestamp() * 1000
        current = None
        for entry in entries:
            if entry["start_timestamp"] <= now_ms < entry["end_timestamp"]:
                current = entry
                break
        current = current or entries[0]

        # aWATTar reports EUR/MWh
        price = _to_ct_per_kwh(float(current["marketprice"]))
        timestamp = datetime.fromtimestamp(
            current["start_timestamp"] / 1000, tz=timezone.utc
        )
        return PriceResult(
            price=price,
            currency="EUR",
            unit="c/kWh",
            timestamp=timestamp,
            source="aWATTar",
            zone=zone.upper(),
            raw=current,
        )


class TibberProvider(BaseProvider):
    """Tibber current price, free for customers but requires a token."""

    info = ProviderInfo(
        id="tibber",
        name="Tibber (current price)",
        tier="free-key",
        requires_key=True,
        zones=["HOME"],
        zone_hint="Uses your first Tibber home; zone is ignored",
        homepage="https://developer.tibber.com",
        needs_token_env="TIBBER_TOKEN",
    )

    async def fetch(self, zone: str, client: httpx.AsyncClient) -> PriceResult:
        token = env_config.tibber_token
        if not token:
            raise ProviderError("TIBBER_TOKEN is not configured in .env")
        query = """
        { viewer { homes { currentSubscription { priceInfo { current {
            total currency startsAt
        } } } } } }
        """
        resp = await client.post(
            "https://api.tibber.com/v1-beta/gql",
            json={"query": query},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        try:
            homes = data["data"]["viewer"]["homes"]
            current = homes[0]["currentSubscription"]["priceInfo"]["current"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"Unexpected Tibber response: {exc}") from exc

        # Tibber 'total' is in currency/kWh (e.g. EUR/kWh) -> convert to cents
        price = round(float(current["total"]) * 100.0, 3)
        return PriceResult(
            price=price,
            currency=current.get("currency", "EUR"),
            unit="c/kWh",
            timestamp=datetime.fromisoformat(current["startsAt"]),
            source="Tibber",
            zone="HOME",
            raw=current,
        )


class EntsoeProvider(BaseProvider):
    """ENTSO-E Transparency Platform - free but requires a security token."""

    _ZONE_EIC = {
        "DE": "10Y1001A1001A82H",   # DE-LU
        "AT": "10YAT-APG------L",
        "FR": "10YFR-RTE------C",
        "BE": "10YBE----------2",
        "NL": "10YNL----------L",
        "CH": "10YCH-SWISSGRIDZ",
        "ES": "10YES-REE------0",
        "PL": "10YPL-AREA-----S",
        "DK1": "10YDK-1--------W",
        "DK2": "10YDK-2--------M",
    }

    info = ProviderInfo(
        id="entsoe",
        name="ENTSO-E Transparency (day-ahead)",
        tier="free-key",
        requires_key=True,
        zones=list(_ZONE_EIC.keys()),
        zone_hint="Bidding zone, e.g. DE, AT, FR",
        homepage="https://transparency.entsoe.eu",
        needs_token_env="ENTSOE_TOKEN",
    )

    async def fetch(self, zone: str, client: httpx.AsyncClient) -> PriceResult:
        import xml.etree.ElementTree as ET

        token = env_config.entsoe_token
        if not token:
            raise ProviderError("ENTSOE_TOKEN is not configured in .env")
        eic = self._ZONE_EIC.get(zone.upper())
        if not eic:
            raise ProviderError(f"Zone '{zone}' is not supported by ENTSO-E provider")

        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        fmt = "%Y%m%d%H00"
        params = {
            "securityToken": token,
            "documentType": "A44",
            "in_Domain": eic,
            "out_Domain": eic,
            "periodStart": start.strftime(fmt),
            "periodEnd": now.strftime(fmt),
        }
        resp = await client.get("https://web-api.tp.entsoe.eu/api", params=params)
        resp.raise_for_status()

        ns = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0"}
        root = ET.fromstring(resp.text)
        points: list[tuple[int, float]] = []
        for period in root.findall(".//ns:Period", ns):
            for point in period.findall("ns:Point", ns):
                pos = int(point.findtext("ns:position", default="0", namespaces=ns))
                amount = float(
                    point.findtext("ns:price.amount", default="0", namespaces=ns)
                )
                points.append((pos, amount))
        if not points:
            raise ProviderError("ENTSO-E returned no price points")

        # Use the latest hourly position as 'current'
        points.sort(key=lambda p: p[0])
        _, eur_mwh = points[-1]
        return PriceResult(
            price=_to_ct_per_kwh(eur_mwh),
            currency="EUR",
            unit="c/kWh",
            timestamp=now.replace(minute=0, second=0, microsecond=0),
            source="ENTSO-E",
            zone=zone.upper(),
        )


# Registry ordered by preference (free first).
_PROVIDERS: dict[str, BaseProvider] = {
    p.info.id: p
    for p in (
        EleczProvider(),
        AwattarProvider(),
        TibberProvider(),
        EntsoeProvider(),
    )
}


def list_providers() -> list[ProviderInfo]:
    """Return metadata for all known providers (preference order)."""
    return [p.info for p in _PROVIDERS.values()]


def get_provider(provider_id: str) -> BaseProvider:
    provider = _PROVIDERS.get(provider_id)
    if provider is None:
        raise ProviderError(f"Unknown provider: {provider_id}")
    return provider


async def fetch_price(provider_id: str, zone: str) -> PriceResult:
    """Fetch and normalise the current price from the given provider."""
    provider = get_provider(provider_id)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        try:
            return await provider.fetch(zone, client)
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"{provider.info.name} HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"{provider.info.name} request failed: {exc}") from exc
