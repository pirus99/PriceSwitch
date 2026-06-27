# PriceSwitch: Energy-Price-Based GPIO Relay Control for Raspberry Pi (2B+)

**PriceSwitch** polls live electricity spot prices, compares them against a user-defined **switch price**, and drives two mutually exclusive relay outputs (`HIGH`/`LOW`). A modern web interface provides a live dashboard and an intuitive settings page.

## Project Goal
Control large electric consumers to use energy when it’s cheapest. By toggling relays, nearly any appliance can be managed—no smart capabilities required. Examples:
- Air conditioning/cooling systems
- Heating elements in buffer containers
- Battery or EV chargers

### Dashboard

<img width="1918" height="908" alt="PriceSwitch_Dashboard" src="https://github.com/user-attachments/assets/1ce69811-c6b9-4e0d-949e-b75127e14a9e" />

## Features

- **Live dashboard** - Displays all important information in a compact View.
- **Settings page** - All important Settings can be accessed over 
  the Web Interface, Security Settings are only available over .env file.
- **Multiple price providers** - The application supports multiple price providers
  | Provider | Tier | Key |
  |----------|------|-----|
  | Elecz.com Spot (ENTSO-E) | free | no |
  | aWATTar (DE/AT) | free | no |
  | Tibber (current price) | free | yes (`TIBBER_TOKEN`) |
  | ENTSO-E Transparency | free | yes (`ENTSOE_TOKEN`) |
- **Price Hysterisis/Threshold** - A switch back threshold can be set to switch back to High output 
  on a slightly Higher price than the actual set Switch Price, also a Timeout can be 
  set that needs to expire before a new Switch event could happen.
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
git clone https://github.com/pirus99/PriceSwitch PriceSwitch
cd PriceSwitch
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set SECRET_KEY, AUTH_REQUIRED/AUTH_PASSWORD, GPIO_ACTIVE_LOW, tokens (only if needed)
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
