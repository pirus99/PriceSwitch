# PriceSwitch

Energy-price based GPIO switch for the Raspberry Pi (2B+ and up).
PriceSwitch polls a live electricity spot price, compares it against a
user-defined **switch price**, and drives two mutually-exclusive relay
outputs (`HIGH` and `LOW`). A modern web interface provides a live
dashboard and a friendly settings page.

## Features

- **Live dashboard** – switch mode, output status, current price, price age,
  and a switch-event log.
- **Settings page** (no raw JSON) – provider, zone, poll interval, switch
  price, threshold, hysteresis, GPIO pins, AUTO/MANUAL mode, manual output,
  and log retention.
- **Multiple price providers**, preferring free/no-key sources:
  | Provider | Tier | Key |
  |----------|------|-----|
  | Elecz.com Spot (ENTSO-E) | free | no |
  | aWATTar (DE/AT) | free | no |
  | Tibber (current price) | free | yes (`TIBBER_TOKEN`) |
  | ENTSO-E Transparency | free | yes (`ENTSOE_TOKEN`) |
- **Safe GPIO control** – `HIGH` and `LOW` are never energised at the same
  time. Active-high/low is configurable in `.env`.
- **Runs anywhere** – automatically simulates GPIO when not on a Pi, so you
  can develop on Windows/macOS/Linux.
- **SQLite event log** with automatic retention cleanup (weeks/months).
- Optional **password login**.

## Switch logic

In **AUTO** mode, on every poll:

- `price <= switch_price` → **LOW** output ON
- `price > switch_price + threshold` → **HIGH** output ON
- in between (the deadband) → keep the current output

A **hysteresis** timer (seconds) blocks any new switch event until the
configured lockout has elapsed since the last switch.

In **MANUAL** mode the price is ignored and the output follows your
manual `HIGH`/`LOW` selection.

## Install (Raspberry Pi)

```bash
git clone <your-repo-url> PriceSwitch
cd PriceSwitch
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set SECRET_KEY, AUTH_REQUIRED/AUTH_PASSWORD, GPIO_ACTIVE_LOW, tokens
python run.py
```

Open `http://<pi-ip>:8000` in a browser.

## Run as a service

```bash
sudo cp priceswitch.service /etc/systemd/system/
# adjust User= and WorkingDirectory= if needed
sudo systemctl daemon-reload
sudo systemctl enable --now priceswitch
```

## Configuration

| Where | What |
|-------|------|
| `.env` | Static settings: host/port, secret key, auth, file paths, GPIO active-low, API tokens. |
| Settings page | Frequently changed: provider, zone, poll interval, switch price, threshold, hysteresis, GPIO pins, mode, manual output, log retention. |

## Development (off-Pi)

GPIO is automatically mocked when `gpiozero` hardware is unavailable, so the
full app (including the switch logic) runs on any machine.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # Windows
python run.py
```
