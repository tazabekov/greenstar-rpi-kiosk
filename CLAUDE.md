# MyGreenStar Kiosk — Claude Context

## Standing instruction

**Keep `README.md` up to date.** Whenever you make a significant change — new feature, bug fix, architecture decision, new known issue — update the relevant section of README.md in the same session. Do not wait to be asked.

Sections most likely to need updating:
- **Current Status** table: update ✅/⏳/❌ when a feature ships or a blocker is found
- **Known Issues / Wayland Notes**: add any new runtime warnings or display quirks
- **Architecture** and **Screen Size Constraints**: update when new screens or signals are added
- **MDB / Square Integration** guides: update when real hardware or credentials arrive

---

## Project at a glance

Coffee vending machine payment kiosk on **Raspberry Pi 5** with an 800×480 capacitive touchscreen.

```
KreaTouch machine → MDB Pi Hat (USB) → RPi5 (this) → Square Web API → Square Terminal
                                                                      ├── FIAT (card)
                                                                      └── ₿ Bitcoin
```

Python 3 / PyQt5. Custom QPainter rendering throughout — no QML, no web views.

## Running

```bash
cd /home/ali/code/greenstar-rpi-kiosk
DISPLAY=:0 python3 main.py      # run on the kiosk display
python3 -m pytest tests/ -v     # run the test suite
```

Escape key quits (dev only). The autostart `.desktop` file launches it on boot.

## Display environment

- Compositor: **labwc** (Wayland)
- App runs via **Xwayland** (DISPLAY=:0)
- Screenshots: `WAYLAND_DISPLAY=wayland-0 grim /tmp/shot.png` — `scrot` sees blank
- `qt.qpa.wayland: Wayland does not support QWindow::requestActivate()` in the log is harmless — this is an Xwayland limitation; the window still receives focus correctly through the compositor

## Key architecture patterns

- **AppBus** (`core/bus.py`) — singleton Qt signal bus. All components talk through it. Add signals there; never call methods on other widgets directly.
- **Signals over `self.window()`** — do not reach up through the widget tree. Use a `pyqtSignal` emitted by the child and wired in `MainWindow`.
- **Custom QPainter** for all data widgets — `paintEvent` + `update()` only; no mixing Qt layout children inside painted regions.
- **`make_square_client()`** auto-selects: returns `SquareClient` when `SQUARE_ACCESS_TOKEN` is in `.env`, otherwise `SquareMockClient`. No code change needed to go live.
- **Touch targets** ≥ 44px tall. Modal card ≤ 420px on 800×480 display (32px taskbar, 20px padding).
- Signal connections made in `__init__` or `_request()` must be disconnected in `closeEvent` / `done()` — see `PaymentModal` and `TransactionDetailModal` for the pattern.

## File map

```
core/bus.py          AppBus signals (source of truth for inter-component API)
core/models.py       Transaction + TransactionEvent dataclasses
core/sampler.py      DataSampler — CPU% and temperature via psutil
core/snapshotter.py      Snapshotter — periodic camera JPEG → Firebase Storage (all cameras)
core/camera_registry.py  CameraRegistry — discovers cameras at startup, per-camera locks,
                         running-cam ref so Snapshotter can capture from live feed directly
core/square.py           SquareMockClient (active) + SquareClient skeleton
core/mdb.py              MDB Pi Hat stub — implement when hardware arrives (~2026-06-23)
ui/theme.py              Colours, button stylesheets, WINDOWS
ui/header.py             HeaderWidget — star, logo, tab nav, clock
ui/screens/              dashboard.py · system.py
ui/widgets/              graph.py · system_mini.py · transaction_list.py
                         payment_modal.py · transaction_detail_modal.py
                         settings_modal.py · camera_modal.py
tests/               pytest + pytest-qt — all passing
.env.example         template — copy to .env and fill in values (gitignored)
```

## Environment variables (`.env`)

All config lives in `.env` (gitignored). Copy `.env.example` → `.env` on each Pi.

```
FIREBASE_SERVICE_ACCOUNT_JSON   full service-account JSON as a single-line string
GKM_KIOSK_ID                    unique kiosk ID (Firestore document key)
GKM_KIOSK_NAME                  display name in the GKM dashboard
GKM_KIOSK_LOCATION              location in the GKM dashboard

SQUARE_ACCESS_TOKEN             set this to activate live Square payments (auto-detected)
SQUARE_LOCATION_ID
SQUARE_DEVICE_ID
SQUARE_ENVIRONMENT              "sandbox" | "production"

GKM_FIREBASE_STORAGE_BUCKET     Firebase Storage bucket (omit gs://) for camera snapshots
GKM_SNAPSHOT_INTERVAL_MIN       minutes between snapshots; 0 = disabled
```
