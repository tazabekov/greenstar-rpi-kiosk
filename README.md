# MyGreenStar Kiosk

Coffee vending machine payment kiosk running on a Raspberry Pi 5 with an 800×480 capacitive touchscreen.

## Purpose

Connect a **KreaTouch coffee vending machine** to a **Square payment terminal** to enable Bitcoin payments — which Cantaloupe / eSoft card readers do not support.

## Hardware Architecture

```
KreaTouch vending machine
        │  MDB protocol
        ▼
MDB Pi Hat  (USB adapter — https://docs.qibixx.com/mdb-products/mdb-pi-hat)
        │  USB serial  /dev/ttyUSB0 or /dev/ttyACM0
        ▼
Raspberry Pi 5  (this device, 800×480 touchscreen)
        │  HTTPS — Square Web API
        ▼
Square Payment Terminal
        │
        ├── FIAT  (card / contactless)
        └── ₿ Bitcoin  (via Cash App Pay — see Square integration notes)
```

## Current Status

| Component | Status |
|---|---|
| CPU / temperature monitoring | ✅ Live |
| Dashboard with transaction log | ✅ Working (sample data) |
| Clickable transactions with event log | ✅ Working |
| Test payment modal (keypad + FIAT/Bitcoin) | ✅ Working (mock Square) |
| Processing screen with live event log + elapsed timer | ✅ Working |
| X-axis time labels on graphs | ✅ Working |
| Time-window selector (1 min/5 min/1 hr/24 hr) | ✅ Working |
| Test suite (77 tests, pytest-qt) | ✅ Passing |
| GKM reporter (heartbeat + transaction sync) | ✅ Implemented — needs Firebase credentials |
| MDB Pi Hat integration | ⏳ Hardware arriving ~2026-06-23 |
| Square Web API integration | ⏳ Needs credentials (see below) |

## Software Architecture

```
greenstar-rpi-kiosk/
├── main.py                     # App entry point, MainWindow, screen routing
├── CLAUDE.md                   # Claude session context (auto-updates README)
├── pytest.ini                  # Test config (qt_api = pyqt5)
├── core/
│   ├── bus.py                  # AppBus singleton — app-wide Qt signals
│   ├── models.py               # Transaction + TransactionEvent dataclasses
│   ├── sampler.py              # DataSampler — CPU % and temperature via psutil
│   ├── reporter.py             # GKM Reporter — heartbeat + transaction sync to Firestore
│   ├── square.py               # SquareMockClient (active) + SquareClient skeleton
│   └── mdb.py                  # MDB Pi Hat stub (to be implemented)
├── ui/
│   ├── theme.py                # Colour palette, button stylesheets, WINDOWS
│   ├── header.py               # HeaderWidget: star icon + logo + tab nav + clock
│   ├── screens/
│   │   ├── dashboard.py        # Transaction log + mini system stats + payment button
│   │   └── system.py           # Full CPU/temp graphs + time-window selector
│   └── widgets/
│       ├── graph.py            # Scrolling line graph with scan-line texture + x-axis
│       ├── system_mini.py      # Compact CPU+temp bar indicators for dashboard sidebar
│       ├── transaction_list.py # Painted transaction log — tap any row to see event log
│       ├── payment_modal.py    # Touch-friendly payment dialog (keypad + FIAT/₿)
│       └── transaction_detail_modal.py  # Timestamped event log per transaction
└── tests/
    ├── conftest.py             # Shared fixtures (qapp, DISPLAY env)
    ├── test_models.py          # Transaction + TransactionEvent (15 tests)
    ├── test_bus.py             # AppBus signal correctness (15 tests)
    ├── test_square_mock.py     # SquareMockClient event sequence (16 tests)
    └── test_payment_modal.py   # Keypad, validation, type toggle (31 tests)
```

### Event Bus (`core/bus.py`)

All components communicate via `bus` (singleton `AppBus`):

| Signal | Signature | Emitted by | Consumed by |
|---|---|---|---|
| `transaction_added` | `Transaction` | PaymentModal, MDB reader | TransactionList |
| `transaction_event` | `tx_id, TransactionEvent` | SquareMockClient / SquareClient | TransactionList, TransactionDetailModal |
| `payment_requested` | `tx_id, amount, type` | PaymentModal | SquareMockClient / SquareClient |
| `payment_result` | `tx_id, success, message` | SquareMockClient / SquareClient | PaymentModal, TransactionList, TransactionDetailModal |

### Transaction Event Log

Each `Transaction` carries an ordered list of `TransactionEvent` objects. A typical FIAT payment sequence:

```
[SYSTEM →]  Payment flow started
[SQUARE →]  POST /v2/terminals/checkouts  $3.90 USD
[SQUARE ←]  200 OK — checkout created, status: PENDING
[SQUARE ←]  GET .../checkout_id → IN_PROGRESS (payment screen shown)
[SQUARE ←]  GET .../checkout_id → COMPLETED (card tapped)
[MDB    →]  VEND APPROVED  0x05 0x00
```

Tap any row in the transaction list to view the full event log with millisecond timestamps.

## Screen Size Constraints

**All screens and modals must fit within 800×480 px.**
The labwc taskbar occupies ~32px at the bottom, leaving ~448px of usable height.

Rules for new UI components:
- Fixed-height widgets: sum all heights + margins + spacing and verify ≤ 440px
- Modals/dialogs: design for ≤ 420px card height; use `card.setMaximumHeight(parent.height() - 40)` as a safety cap
- Font sizes: 28pt hero numbers fit in 52px strips; 15pt body fits in 24px rows
- Touch targets: **minimum 44px tall, minimum 80px wide** for primary actions
- Close buttons on modals: use a full-width bottom bar (52px) — top-corner buttons are unreachable one-handed

Quick height budget for a full-screen dialog:
```
480px total
 -32px taskbar
 -20px overlay padding (top + bottom)
= 428px available for the card
```

## Running

```bash
python3 main.py
```

Press **Esc** to quit (development only).

### Test suite

```bash
python3 -m pytest tests/ -v
```

77 tests, 0 failures. Covers models, AppBus signals, Square mock event sequence, and PaymentModal logic.

## Display Notes

This Pi runs **labwc** (Wayland compositor) with **Xwayland** in rootless mode.

- Launch with `DISPLAY=:0 python3 main.py` (X11 path through Xwayland → labwc)
- Screenshots: use `WAYLAND_DISPLAY=wayland-0 grim /tmp/shot.png` — `scrot` captures a blank Xwayland framebuffer
- Autostart: `~/.config/autostart/mygreenstar-kiosk.desktop` (XDG autostart, 3s delay)

### Known Wayland warnings

```
qt.qpa.wayland: Wayland does not support QWindow::requestActivate()
```

This line appears in the log and is **harmless**. Xwayland windows cannot request focus directly via the X11 `_NET_ACTIVE_WINDOW` hint — focus is managed by the Wayland compositor (labwc). The kiosk window still receives input and renders correctly. The warning fires on startup and can be ignored.

## MDB Pi Hat Integration (`core/mdb.py`)

Hardware arrives ~2026-06-23. See `core/mdb.py` for the planned interface.

Steps to wire up:
1. Connect MDB Pi Hat USB → RPi5
2. Confirm device node: `ls /dev/ttyUSB* /dev/ttyACM*`
3. Implement `MdbReader(QObject)` in `core/mdb.py` using `pyserial`
4. On each vend event, create a `Transaction` (status="pending") and call `bus.transaction_added.emit(tx)`
5. Emit `bus.payment_requested(tx.tx_id, amount, "fiat")` to trigger Square checkout
6. On `bus.payment_result`, emit MDB VEND APPROVED or VEND DENIED to the machine

Install pyserial when ready: `pip3 install pyserial`

## Square Integration (`core/square.py`)

### Active: SquareMockClient

During development, `SquareMockClient` in `main.py` simulates the full Square Terminal API flow with realistic timing (fiat: ~6s, Bitcoin: ~8s). All event log entries are generated; no network calls are made.

### Going live: SquareClient

1. Create `.env` with:
   ```
   SQUARE_ACCESS_TOKEN=sandbox-sq0idp-...
   SQUARE_LOCATION_ID=L...
   SQUARE_DEVICE_ID=device:...
   SQUARE_ENVIRONMENT=sandbox
   ```

2. Find your `SQUARE_DEVICE_ID`:
   ```bash
   curl https://connect.squareupsandbox.com/v2/devices \
        -H "Authorization: Bearer YOUR_SANDBOX_TOKEN" \
        -H "Square-Version: 2025-01-23"
   ```

3. Install deps: `pip3 install requests python-dotenv`

4. In `main.py` line 13, change:
   ```python
   from core.square import SquareMockClient   # swap for SquareClient when live
   ```
   to:
   ```python
   from core.square import SquareClient as SquareMockClient
   ```

5. Connect `bus.payment_requested` → `SquareClient.request_payment()` (already wired in `main.py`)

### Bitcoin / Square Terminal

Square Terminal API does not natively support Bitcoin. Recommended path:
- **Cash App Pay** — Square terminals can offer Cash App Pay as a payment method, which supports crypto (incl. BTC). Enable via `payment_options.crypto_enabled: true` in the checkout body (already in `SquareMockClient` and `SquareClient`).
- Confirm with Square developer support whether your terminal hardware supports Cash App Pay before going live.

## GreenStar Kiosk Manager (GKM) Integration (`core/reporter.py`)

GKM is a separate web dashboard (`greenstar-kiosk-manager` repo) that monitors multiple kiosks in real time.

### How it works

`Reporter` runs as a background object in `MainWindow`. Every 60 seconds it:
- Writes the latest `cpu_percent`, `temperature_c`, and `last_heartbeat` to Firestore
- Adds a timestamped document to the `metrics` subcollection (history for sparklines)
- Self-registers the kiosk on first run (creates `/kiosks/{kiosk_id}` if it doesn't exist)

On every `transaction_added` / `transaction_event` signal it immediately syncs that transaction to the `transactions` subcollection.

If `firebase-admin` is not installed or the env vars are missing, `Reporter` logs a warning and no-ops — the kiosk continues to function normally.

### Setup

1. Create a Firebase project at https://console.firebase.google.com
2. Enable **Firestore** and **Google Authentication**
3. Create a service account (Project settings → Service accounts → Generate new private key)
4. Copy the JSON key to the Pi, e.g. `/home/pi/greenstar-key.json`
5. Add to `.env`:
   ```
   FIREBASE_SERVICE_ACCOUNT_PATH=/home/pi/greenstar-key.json
   GKM_KIOSK_ID=kiosk-001
   GKM_KIOSK_NAME=Kiosk #1 – Main Floor
   GKM_KIOSK_LOCATION=Seattle, WA
   ```
6. Install the dependency: `pip3 install firebase-admin`

### Status in Current Status table

| Component | Status |
|---|---|
| GKM reporter (`core/reporter.py`) | ✅ Implemented — awaiting Firebase credentials |

---

## Autostart on Boot

```ini
# ~/.config/autostart/mygreenstar-kiosk.desktop
[Desktop Entry]
Name=MyGreenStar Kiosk
Exec=/usr/bin/python3 /home/ali/code/greenstar-rpi-kiosk/main.py
Type=Application
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=3
```
