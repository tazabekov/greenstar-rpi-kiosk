# MyGreenStar Kiosk

> **Part of the GreenStar system.** The web dashboard and system brain lives at [`greenstar-kiosk-manager`](https://github.com/tazabekov/greenstar-kiosk-manager) — that repo is the authoritative source for architecture, registered kiosks, and deployment info.

Coffee vending machine payment kiosk running on a Raspberry Pi 5 with an 800×480 capacitive touchscreen.

## Purpose

Connect a **KreaTouch coffee vending machine** to a **Square payment terminal** to enable Bitcoin payments — which Cantaloupe / eSoft card readers do not support.

## Hardware Architecture

```
KreaTouch vending machine
        │  MDB protocol  (Right / Peripheral port on hat — see MDB section)
        ▼
MDB Pi Hat  (https://docs.qibixx.com/mdb-products/mdb-pi-hat)
        │  USB serial /dev/ttyACM0  (or UART /dev/ttyS0 on Pi 5)
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
| Test suite (213 tests, pytest-qt) | ✅ Passing |
| GKM reporter (heartbeat + transaction sync) | ✅ Live — syncing to Firestore every 60 s |
| Camera live view | ✅ Any attached camera; side-by-side for 2, tabs for 3+ |
| Periodic camera snapshot → Firebase Storage | ✅ All cameras snapshotted; works during live feed |
| Hardware status strip (throttle/fan/disk) | ✅ Live on System screen |
| Health status indicator | ✅ Shipped — green/yellow/red status in header and System screen |
| MDB Pi Hat integration | ✅ Implemented — `core/mdb.py` (cashless peripheral mode) |
| Square Web API integration | ✅ Live — Square Terminal paired, production credentials set |
| Crypto payment mode | ✅ Shipped — Firestore session listener, Terminal QR action, amber header pill |

## Software Architecture

```
greenstar-rpi-kiosk/
├── main.py                     # App entry point, MainWindow, screen routing
├── CLAUDE.md                   # Claude session context (auto-updates README)
├── pytest.ini                  # Test config (qt_api = pyqt5)
├── core/
│   ├── bus.py                  # AppBus singleton — app-wide Qt signals
│   ├── models.py               # Transaction + TransactionEvent dataclasses
│   ├── sampler.py              # DataSampler — CPU%, temperature, fan, disk, throttle signals via psutil
│   ├── health.py               # HealthMonitor — aggregates cpu/temp/disk/throttle/camera/firestore/mdb
│   ├── reporter.py             # GKM Reporter — heartbeat + transaction sync to Firestore
│   ├── snapshotter.py          # Snapshotter — periodic camera JPEG → Firebase Storage (all cameras)
│   ├── camera_registry.py      # CameraRegistry — discovers cameras, per-camera locks + running-cam ref
│   ├── square.py               # SquareMockClient (active) + SquareClient
│   ├── crypto_session.py       # CryptoSessionManager — Firestore listener + Terminal QR + BitPay polling
│   ├── bitpay.py               # BitPayMockClient (active) + BitPayClient stub; make_bitpay_client()
│   └── mdb.py                  # MdbReader — cashless peripheral; bridges KreaTouch vends to Square
├── ui/
│   ├── theme.py                # Colour palette, button stylesheets, WINDOWS
│   ├── header.py               # HeaderWidget: star icon + logo + tab nav + clock
│   ├── screens/
│   │   ├── dashboard.py        # Transaction log + mini system stats + payment button
│   │   └── system.py           # Full CPU/temp graphs + time-window selector
│   └── widgets/
│       ├── graph.py            # Scrolling line graph with scan-line texture + x-axis
│       ├── system_mini.py      # Compact CPU+temp bar indicators for dashboard sidebar
│       ├── hardware_status.py   # HardwareStatusBar — throttle/fan/disk status strip on System screen
│       ├── transaction_list.py # Painted transaction log — tap any row to see event log
│       ├── payment_modal.py    # Touch-friendly payment dialog (keypad + FIAT/₿)
│       ├── transaction_detail_modal.py  # Timestamped event log per transaction
│       ├── settings_modal.py   # Gear-button modal: Name, Location, Kiosk ID, Snapshot Interval
│       └── camera_modal.py     # Live camera view — auto-detects cameras, side-by-side or tabbed
└── tests/
    ├── conftest.py             # Shared fixtures (qapp, DISPLAY env)
    ├── test_models.py          # Transaction + TransactionEvent (15 tests)
    ├── test_bus.py             # AppBus signal correctness (15 tests)
    ├── test_square_mock.py     # SquareMockClient event sequence (16 tests)
    ├── test_payment_modal.py   # Keypad, validation, type toggle (31 tests)
    ├── test_camera_registry.py # CameraRegistry probe, locks, running-cam ref (5 tests)
    ├── test_camera_modal.py    # CameraModal layout + panel lifecycle + header button (11 tests)
    ├── test_snapshotter.py     # Snapshotter — idle/live capture paths + settings (19 tests)
    ├── test_crypto_session.py  # CryptoSessionManager state machine + BitPay wiring (16 tests)
    └── test_bitpay.py          # BitPayMockClient, BitPayClient stub, make_bitpay_client() (10 tests)
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
| `firestore_ok_changed` | `bool` | Reporter (after each 60 s heartbeat) | HealthMonitor |
| `camera_ok_changed` | `bool` | MainWindow (once at startup) | HealthMonitor |
| `payment_cancel_requested` | `tx_id` | PaymentModal (Cancel button) | SquareClient |
| `crypto_session_changed` | `session dict \| None` | CryptoSessionManager | HeaderWidget (pill) |
| `mdb_ok_changed` *(on MdbReader)* | `bool` | MdbReader | HealthMonitor (`on_mdb_ok`) |

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

213 tests, 0 failures. Covers models, AppBus signals, Square mock event sequence, PaymentModal logic, camera registry, camera modal, Snapshotter, CryptoSessionManager state machine, and BitPay client.

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

`MdbReader` runs as a background `QThread`. It opens the Pi Hat serial port, configures the hat as a **cashless peripheral** (MDB address `0x10`), and bridges every KreaTouch vend event into the Square/crypto payment flow.

### Hardware connection

```
KreaTouch  →  MDB cable  →  Right (Peripheral) port on Pi Hat
                             ↑ NOT the left port — that's the VMC/master side
Pi Hat  →  USB  →  RPi5   /dev/ttyACM0
      or   UART GPIO        /dev/ttyS0  (Pi 5 only)
```

**Jumper Set 1** must be **REMOVED** (Split Mode). Do not install them horizontally — that's sniff mode, which bridges both ports and prevents cashless peripheral operation.

**USB Toggle Jumper** (on Pi Hat): must be **closed** when using USB, **open** for UART.

### Setup

```bash
pip3 install pyserial

# Quick sanity check — should return firmware version:
sudo minicom -b 115200 -D /dev/ttyACM0
# type V then Enter → v,<version>,<serial>

# If using UART (Pi 5 GPIO), first enable it:
# /boot/firmware/config.txt:
#   dtoverlay=disable-bt
#   enable_uart=1
#   dtparam=uart0=on
# /boot/firmware/cmdline.txt: remove console=serial0,115200
# sudo systemctl disable hciuart
# reboot
```

### Serial protocol (Pi Hat API)

All commands are plain text, `\n`-terminated, 115200 8N1.

| We send | Hat/VMC responds | Meaning |
|---|---|---|
| `C,SETCONF,mdb-addr=0x10` | — | Set cashless peripheral address |
| `C,1` | `c,STATUS,ENABLED` | Enable; VMC acknowledged us |
| (listen) | `c,STATUS,VEND,1.50,3` | Customer selected item 3 at $1.50 |
| `C,VEND,1.50` | `c,VEND,SUCCESS` | Approve — KreaTouch dispenses |
| `C,STOP` | — | Deny — KreaTouch cancels vend |
| `C,0` | — | Disable peripheral (sent on shutdown) |

### Vend flow

```
KreaTouch selects item
  → c,STATUS,VEND,<amount>,<item>          (MDB in)
  → Transaction created (status=pending)
  → bus.transaction_added(tx)
  → bus.payment_requested(tx_id, amount, type)
      → SquareClient / CryptoSessionManager
          → payment completes / fails
  → bus.payment_result(tx_id, success, msg)
  → C,VEND,<amount>  (approve)             (MDB out)
     or C,STOP        (deny)
```

### Environment variable

```
GKM_MDB_PORT=    # leave blank to auto-detect (checks ttyACM0, ttyUSB0, ttyS0)
```

### First-time setup checklist (run after reconnecting hardware)

```bash
# 1. Install pyserial if not yet installed
pip3 install pyserial

# 2. Confirm Pi Hat is visible on USB
ls /dev/ttyACM* /dev/ttyUSB*        # expect /dev/ttyACM0

# 3. Sanity-check: Pi Hat responds to version query
#    (Ctrl-A X to exit minicom)
sudo minicom -b 115200 -D /dev/ttyACM0
#    type:  V  then Enter
#    expect: v,<firmware-version>,<serial-number>

# 4. Start the kiosk
DISPLAY=:0 python3 main.py
# Watch the log for:
#   MDB: opened /dev/ttyACM0 at 115200 baud
#   MDB: peripheral enabled — waiting for vend requests
# If you see "INACTIVE", KreaTouch is not talking to the hat —
# double-check the Right port and jumpers (see Hardware connection above).
```

### Jumper reference (Pi Hat top view, USB on left)

```
  [Left port — VMC master]     [Right port — Peripheral/slave]  ← KreaTouch goes here
         │                              │
  Jumper Set 1:  REMOVE both jumpers  (horizontal = sniff mode — wrong for us)
  USB Toggle Jumper: CLOSE  (needed for USB /dev/ttyACM0 mode)
```

### Health indicator

`MdbReader` emits `mdb_ok_changed(bool)` which feeds `HealthMonitor`. The header turns **red** if the hat stops responding or reports `INACTIVE`. If `GKM_MDB_PORT` is unset and no port is auto-detected, the reader is disabled and health stays green.

## Square Integration (`core/square.py`)

### Required hardware: Square Terminal

The Terminal API only works with the **Square Terminal** (the dedicated countertop device, ~$299) or Square Register. **Square Handheld does not support Terminal API** — it is a standalone POS device and cannot receive remote checkout requests from the API. Square Reader dongles also do not support Terminal API.

For the kiosk vending machine use case, Square Terminal is the correct hardware: the customer taps their card on the countertop terminal while the kiosk screen shows the payment flow.

### Active: SquareMockClient

During development, `SquareMockClient` in `main.py` simulates the full Square Terminal API flow with realistic timing (fiat: ~6s, Bitcoin: ~8s). All event log entries are generated; no network calls are made.

### Going live: SquareClient

1. Create `.env` with:
   ```
   SQUARE_ACCESS_TOKEN=sq0atp-...   # production token from developer.squareup.com
   SQUARE_LOCATION_ID=L...
   SQUARE_DEVICE_ID=device:...      # from GET /v2/devices after pairing (see below)
   SQUARE_ENVIRONMENT=production
   ```

2. Pair your Square Terminal via device code:

   **Step 1 — generate the code** (expires in 5 minutes):
   ```bash
   curl -s -X POST https://connect.squareup.com/v2/devices/codes \
     -H "Authorization: Bearer $(grep SQUARE_ACCESS_TOKEN .env | cut -d= -f2)" \
     -H "Content-Type: application/json" \
     -H "Square-Version: 2025-01-23" \
     -d "{
       \"idempotency_key\": \"$(cat /proc/sys/kernel/random/uuid)\",
       \"device_code\": {
         \"product_type\": \"TERMINAL_API\",
         \"location_id\": \"$(grep SQUARE_LOCATION_ID .env | cut -d= -f2)\"
       }
     }" | python3 -m json.tool
   ```
   Note the `"code"` field — a 6-letter string.

   **Step 2 — enter the code on the terminal:**
   The Square Terminal must be at the **Sign-in screen** (not already signed in to a Square account).
   Tap **Sign in → Use a device code** → enter the 6-letter code → tap **Sign in**.
   The terminal shows **"Powered by Square"** on success.

   > **Note:** The menu path **≡ → Settings → General → Terminal API Pairing** does NOT exist on current firmware. The correct entry point is the Sign-in screen's "Use a device code" button.

3. Get your `SQUARE_DEVICE_ID` after pairing:
   ```bash
   curl -s https://connect.squareup.com/v2/devices \
        -H "Authorization: Bearer $(grep SQUARE_ACCESS_TOKEN .env | cut -d= -f2)" \
        -H "Square-Version: 2025-01-23" | python3 -m json.tool
   ```
   The response `"id"` field has a `device:` prefix (e.g. `device:614VS149C4002771`). **Strip the prefix** — use only the serial number (`614VS149C4002771`) as `SQUARE_DEVICE_ID`. The Terminal Checkout API rejects the prefixed form with "Merchant not authorized".

4. Install deps: `pip3 install requests python-dotenv`

5. `main.py` calls `make_square_client()` which automatically returns `SquareClient` when `SQUARE_ACCESS_TOKEN` is present, or `SquareMockClient` otherwise. No code change needed — just set the env var.

6. `bus.payment_requested` → `SquareClient.request_payment()` is already wired in `main.py`.

### Crypto Payment Mode (`core/crypto_session.py`, `core/bitpay.py`)

When crypto mode is active the kiosk bypasses Square FIAT checkout and posts a **`QR_CODE` Terminal Action** to the Square Terminal instead, showing a payment QR the customer scans with their phone.

**How it works:**

```
Customer phone
    │  scan static QR image on Square Terminal (uploaded via Square Dashboard)
    ▼
kiosk-manager web app  (/enable-crypto/[kiosk_id])
    │  write to Firestore: /kiosks/{id}/crypto_sessions/active
    ▼
CryptoSessionManager  (on_snapshot listener)
    │  sets bus.crypto_mode = True, bus.crypto_coin = "BTC"
    │  amber pill appears in kiosk header: ⟳ CRYPTO · BTC
    ▼
Payment trigger (MDB vend, manual modal, or direct Bitcoin selection)
    │  SquareClient skips — CryptoSessionManager intercepts
    ▼
_CryptoQRWorker  (QThread)
    │  BitPayClient.create_invoice() → (invoice_id, payment_url)
    │  POST /v2/terminals/actions  (type: QR_CODE, barcode_contents: payment_url)
    │  writes payment_shown to Firestore (amount_usd, payment_link, expires_at)
    ▼
Square Terminal shows payment QR for 60 s
    │  _poll_timer fires every 5 s → BitPayClient.get_invoice_status(invoice_id)
    ├── paid/confirmed/complete → writes status: "paid" to Firestore → session cleared
    └── expired → session cleared
```

**Three payment trigger paths:**
- **Path A** — MDB vend signal fires while `bus.crypto_mode == True`
- **Path B** — operator enters amount in payment modal while crypto mode active
- **Path C** — operator selects Bitcoin directly in payment modal (no prior web session); session written to Firestore with `session_owner: "kiosk"`

**Env vars:**
```
GKM_KIOSK_ID          must be set (also needed for Firestore in general)
SQUARE_ACCESS_TOKEN   must be set (same as FIAT mode)
SQUARE_DEVICE_ID      must be set
BITPAY_API_KEY        optional — leave blank to use BitPayMockClient (simulates paid after 10 s)
```

**BitPay client selection** (same pattern as Square):
- `BITPAY_API_KEY` set → `BitPayClient` (real API — credentials pending)
- `BITPAY_API_KEY` not set → `BitPayMockClient` (auto-reports paid after 10 s for dev/test)

**Terminal idle screen:** The static background image (showing the crypto invite QR code) is uploaded directly via the Square Dashboard — the kiosk app does not post any QR actions on startup or while idle.

### Bitcoin via Square Terminal

Square Terminal API does not natively support Bitcoin as a checkout type. The crypto payment flow above is the recommended path (QR code + external processor).

## Camera Snapshot Upload (`core/snapshotter.py`)

Every `GKM_SNAPSHOT_INTERVAL_MIN` minutes, the kiosk discovers all attached cameras via `CameraRegistry.probe()` and captures a JPEG from each, uploading to **Firebase Storage** at:

```
kiosks/{kiosk_id}/camera0/last-snapshot.jpg
kiosks/{kiosk_id}/camera1/last-snapshot.jpg
kiosks/{kiosk_id}/camera2/last-snapshot.jpg
... (one per detected camera)
```

Each path is overwritten on each snapshot cycle (no accumulation). After a successful upload, the kiosk Firestore document is stamped with:

```
last_snapshot_path           — Storage path for camera 0 (backward-compat field)
last_snapshot_at             — Firestore SERVER_TIMESTAMP
last_snapshot_path_camera1   — Storage path for camera 1 (if present)
last_snapshot_path_camera2   — Storage path for camera 2 (if present)
... (one per camera)
```

The web dashboard reads these fields from the kiosk Firestore document to show a **Camera** row inside the Kiosk Health card on the kiosk detail page (time-ago format, "View" link opens the snapshot modal). These fields are written by `Snapshotter` after each successful upload.

The **Camera Modal** (`CameraModal`) detects all cameras at startup and displays them with model name and max resolution (e.g., "IMX708 · 4608×3456 · ● Live"). Layout adapts by camera count: 1 camera = single full-screen panel; 2 cameras = side-by-side; 3+ cameras = tabbed view.

**Configuration** (in `.env`):

```
GKM_FIREBASE_STORAGE_BUCKET=myproject.appspot.com   # omit gs://
GKM_SNAPSHOT_INTERVAL_MIN=5                         # 0 = disabled
```

The interval can also be changed at runtime via **Settings → Advanced → Snapshot Interval** — no restart needed.

**Snapshot during live feed:** If the Camera Modal is open when a snapshot is due, the Snapshotter captures directly from the already-running `Picamera2` instance (retrieved via `registry.get_running_cam(idx)`) — no lock acquisition is needed and AE/AWB is already converged, so the 2-second warmup is skipped. If the modal is closed, the Snapshotter acquires the per-camera lock, starts its own `Picamera2` instance, waits 2 s for AE/AWB convergence, captures, and closes. The per-camera lock in `core/camera_registry.py` prevents two independent `Picamera2` instances from opening the same camera simultaneously — concurrent opens corrupt picamera2's global listener thread.

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
