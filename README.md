# MyGreenStar Kiosk

> **Part of the GreenStar system.** The web dashboard and system brain lives at [`greenstar-kiosk-manager`](https://github.com/tazabekov/greenstar-kiosk-manager) — that repo is the authoritative source for architecture, registered kiosks, and deployment info.

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
| Test suite (105 tests, pytest-qt) | ✅ Passing |
| GKM reporter (heartbeat + transaction sync) | ✅ Live — syncing to Firestore every 60 s |
| Camera live view | ✅ OV5647 via CSI; conditional camera button in header |
| Periodic camera snapshot → Firebase Storage | ✅ Configurable in Settings → Advanced |
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
│   ├── snapshotter.py          # Snapshotter — periodic camera JPEG → Firebase Storage
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
│       ├── transaction_detail_modal.py  # Timestamped event log per transaction
│       ├── settings_modal.py   # Gear-button modal: Name, Location, Kiosk ID, Snapshot Interval
│       └── camera_modal.py     # Full-screen live camera view (OV5647)
└── tests/
    ├── conftest.py             # Shared fixtures (qapp, DISPLAY env)
    ├── test_models.py          # Transaction + TransactionEvent (15 tests)
    ├── test_bus.py             # AppBus signal correctness (15 tests)
    ├── test_square_mock.py     # SquareMockClient event sequence (16 tests)
    ├── test_payment_modal.py   # Keypad, validation, type toggle (31 tests)
    ├── test_camera_modal.py    # CameraModal + header button (10 tests)
    └── test_snapshotter.py     # Snapshotter + settings interval field (13 tests)
```

### Event Bus (`core/bus.py`)

All components communicate via `bus` (singleton `AppBus`):

| Signal | Signature | Emitted by | Consumed by |
|---|---|---|---|
| `transaction_added` | `Transaction` | PaymentModal, MDB reader | TransactionList |
| `transaction_event` | `tx_id, TransactionEvent` | SquareMockClient / SquareClient | TransactionList, TransactionDetailModal |
| `payment_requested` | `tx_id, amount, type` | PaymentModal | SquareMockClient / SquareClient |
| `payment_result` | `tx_id, success, message` | SquareMockClient / SquareClient | PaymentModal, TransactionList, TransactionDetailModal |
| `settings_changed` | `name, location, kiosk_id` | SettingsModal | Reporter (`on_settings_changed`) |
| `snapshot_interval_changed` | `minutes` | SettingsModal | Snapshotter (`set_interval`) |

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

105 tests, 0 failures. Covers models, AppBus signals, Square mock event sequence, PaymentModal logic, camera modal, and Snapshotter.

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

4. `main.py` calls `make_square_client()` which automatically returns `SquareClient` when `SQUARE_ACCESS_TOKEN` is present, or `SquareMockClient` otherwise. No code change needed — just set the env var.

5. `bus.payment_requested` → `SquareClient.request_payment()` is already wired in `main.py`.

### Bitcoin / Square Terminal

Square Terminal API does not natively support Bitcoin. Recommended path:
- **Cash App Pay** — Square terminals can offer Cash App Pay as a payment method, which supports crypto (incl. BTC). Enable via `payment_options.crypto_enabled: true` in the checkout body (already in `SquareMockClient` and `SquareClient`).
- Confirm with Square developer support whether your terminal hardware supports Cash App Pay before going live.

## Camera Snapshot Upload (`core/snapshotter.py`)

Every `GKM_SNAPSHOT_INTERVAL_MIN` minutes, the kiosk captures a JPEG from the OV5647 camera and uploads it to **Firebase Storage** at:

```
kiosks/{kiosk_id}/camera0/last-snapshot.jpg
```

The same path is overwritten each time (no accumulation). After a successful upload, the kiosk Firestore document is stamped with:

```
last_snapshot_path   — Storage path string
last_snapshot_at     — Firestore SERVER_TIMESTAMP
```

The web dashboard reads `last_snapshot_path` and `last_snapshot_at` from the kiosk Firestore document to show a **Camera** row inside the Kiosk Health card on the kiosk detail page (time-ago format, "View" link opens the full snapshot modal). These fields are written by `Snapshotter` after each successful upload.

**Configuration** (in `.env`):

```
GKM_FIREBASE_STORAGE_BUCKET=myproject.appspot.com   # omit gs://
GKM_SNAPSHOT_INTERVAL_MIN=5                         # 0 = disabled
```

The interval can also be changed at runtime via **Settings → Advanced → Snapshot Interval** — no restart needed.

If the Camera Modal is open when a snapshot is due, the snapshot is silently skipped and retried at the next interval (both use `Picamera2(0)` and cannot run concurrently).

If `picamera2` is not installed, `firebase-admin` is missing, or the env vars are unset, `Snapshotter` logs a warning and no-ops.

---

## GreenStar Kiosk Manager (GKM) Integration (`core/reporter.py`)

GKM is a separate web dashboard at **https://greenstar-kiosk-manager.vercel.app** (repo: `greenstar-kiosk-manager`).  
It monitors all kiosks in real time — live CPU/temperature, online/offline status, and transaction history.  
Sign in with a Google account. Data is stored in Firestore project `greenstar-kiosk-mgr`.

### How it works

`Reporter` runs as a background object in `MainWindow`. Every 60 seconds it:
- Writes the latest `cpu_percent`, `temperature_c`, and `last_heartbeat` to Firestore
- Adds a timestamped document to the `metrics` subcollection (history for sparklines)
- Self-registers the kiosk on first run (creates `/kiosks/{kiosk_id}` if it doesn't exist)

On every `transaction_added` / `transaction_event` signal it immediately syncs that transaction to the `transactions` subcollection.

If `firebase-admin` is not installed or the env vars are missing, `Reporter` logs a warning and no-ops — the kiosk continues to function normally.

### Current Pi config (01-test-kiosk)

`.env` in the repo root (gitignored):

```
FIREBASE_SERVICE_ACCOUNT_JSON='{ ...full JSON key as single line... }'
GKM_KIOSK_ID='01-test-kiosk'
GKM_KIOSK_NAME='Santelli Starkey Ranch'
GKM_KIOSK_LOCATION='Odessa, FL'
```

See `.env.example` for the full field list including Square credentials.

### Adding a new kiosk

```bash
git clone https://github.com/tazabekov/greenstar-rpi-kiosk
cd greenstar-rpi-kiosk
bash scripts/setup_pi.sh
```

`setup_pi.sh` installs Python deps, copies `.env.example` → `.env`, creates the autostart entry (`~/.config/autostart/`), and adds a desktop shortcut (`~/Desktop/`).

After running it:
1. Edit `.env` — paste the Firebase service-account JSON into `FIREBASE_SERVICE_ACCOUNT_JSON`, set a unique `GKM_KIOSK_ID`, and fill in name/location.
2. Reboot — the kiosk starts automatically on login.

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
