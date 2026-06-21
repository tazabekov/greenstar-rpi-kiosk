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
        └── ₿ Bitcoin  (Square crypto payment option)
```

## Current Status

| Component | Status |
|---|---|
| CPU / temperature monitoring | ✅ Live |
| Dashboard with transaction log | ✅ Working (sample data) |
| Test payment modal (keypad + FIAT/Bitcoin) | ✅ Working (simulated) |
| X-axis time labels on graphs | ✅ Working |
| MDB Pi Hat integration | ⏳ Hardware arriving ~2026-06-23 |
| Square Web API integration | ⏳ Needs API key + terminal ID |

## Software Architecture

```
rpi-kiosk/
├── main.py                     # App entry point, MainWindow, screen routing
├── core/
│   ├── bus.py                  # AppBus singleton — app-wide Qt signals
│   ├── models.py               # Transaction dataclass
│   ├── sampler.py              # DataSampler — CPU % and temperature via psutil
│   ├── mdb.py                  # MDB Pi Hat stub (to be implemented)
│   └── square.py               # Square Web API stub (to be implemented)
├── ui/
│   ├── theme.py                # Colour palette, button stylesheets, INTERVALS
│   ├── header.py               # HeaderWidget: star icon + logo + tab nav + clock
│   ├── screens/
│   │   ├── dashboard.py        # Transaction log + mini system stats + payment button
│   │   └── system.py           # Full CPU/temp graphs + interval selector
│   └── widgets/
│       ├── graph.py            # Scrolling line graph with scan-line texture + x-axis
│       ├── system_mini.py      # Compact CPU+temp bar indicators for dashboard sidebar
│       ├── transaction_list.py # Painted transaction log (time, item, amount, type)
│       └── payment_modal.py    # Touch-friendly payment dialog (keypad + FIAT/₿)
└── README.md
```

### Event Bus (`core/bus.py`)

All components communicate via `bus` (singleton `AppBus`):

| Signal | Emitted by | Consumed by |
|---|---|---|
| `transaction_added(Transaction)` | MDB reader (future), payment modal | `TransactionList` |
| `payment_requested(amount, type)` | `PaymentModal` | Square client (future) |
| `payment_result(success, message)` | Square client (future) | `PaymentModal` |

## Running

```bash
python3 main.py
```

Press **Esc** to quit (development only).

## Display Notes

This Pi runs **labwc** (Wayland compositor) with **Xwayland** in rootless mode.

- Launch with `DISPLAY=:0 python3 main.py` (X11 path through Xwayland → labwc)
- Screenshots: use `WAYLAND_DISPLAY=wayland-0 grim /tmp/shot.png` — `scrot` captures a blank Xwayland framebuffer
- Autostart: `~/.config/autostart/mygreenstar-kiosk.desktop` (XDG autostart, 3s delay)

## MDB Pi Hat Integration (`core/mdb.py`)

Hardware arrives ~2026-06-23. See `core/mdb.py` for the planned interface.

Steps to wire up:
1. Connect MDB Pi Hat USB → RPi5
2. Confirm device node: `ls /dev/ttyUSB* /dev/ttyACM*`
3. Implement `MdbReader(QObject)` in `core/mdb.py` using `pyserial`
4. On each vend event, create a `Transaction` and call `bus.transaction_added.emit(tx)`

Install pyserial when ready: `pip3 install pyserial`

## Square Integration (`core/square.py`)

See `core/square.py` for the planned interface.

Steps to wire up:
1. Create `.env` with:
   ```
   SQUARE_API_KEY=sandbox-...
   SQUARE_TERMINAL_ID=...
   SQUARE_LOCATION_ID=...
   SQUARE_ENVIRONMENT=sandbox
   ```
2. Install SDK: `pip3 install squareup python-dotenv`
3. Implement `SquareClient` in `core/square.py`
4. Connect `bus.payment_requested` → `SquareClient.request_payment()`
5. On terminal response, emit `bus.payment_result(success, message)`

## Autostart on Boot

```ini
# ~/.config/autostart/mygreenstar-kiosk.desktop
[Desktop Entry]
Name=MyGreenStar Kiosk
Exec=/usr/bin/python3 /home/ali/code/rpi-kiosk/main.py
Type=Application
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=3
```
