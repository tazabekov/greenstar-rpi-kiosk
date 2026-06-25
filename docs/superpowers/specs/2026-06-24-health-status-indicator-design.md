# Health Status Indicator & Tab Font Fix — Design Spec

Date: 2026-06-24

## Summary

Two UI improvements to the kiosk header and System screen:
1. Shrink the "Dashboard" tab button font so the word fits comfortably.
2. Add a green/yellow/red health indicator dot on the System tab button (visible from any screen) and a one-line status summary on the System screen.

---

## Change 1: Tab Button Font Size

**File:** `ui/theme.py`

Reduce `font-size` in `BTN_ACTIVE` and `BTN_INACTIVE` from `15pt` to `13pt`. Both tab buttons shrink proportionally. No other layout changes needed.

---

## Change 2: Health Status Indicator

### Architecture Overview

```
DataSampler (cpu, temp, disk, throttle)  ──┐
bus.camera_ok_changed                    ──┤──▶  HealthMonitor  ──▶  health_changed(color, reason)
bus.firestore_ok_changed                 ──┘          │
                                                       ├──▶  HeaderWidget.update_system_health()
                                                       └──▶  SystemScreen.update_health()
```

### New: `core/health.py` — `HealthMonitor(QObject)`

Subscribes to sampler signals and two AppBus signals. On every update, runs priority-ordered rules and emits `health_changed(color: str, reason: str)`.

**Signal:** `health_changed = pyqtSignal(str, str)` — (color, reason)

**Thresholds (fixed):**

| Priority | Color | Condition |
|----------|-------|-----------|
| 1 | `"red"` | `_firestore_ok == False` |
| 2 | `"yellow"` | `_camera_ok == False` |
| 2 | `"yellow"` | Throttle current flags active (bitmask bits 0–3 non-zero) |
| 2 | `"yellow"` | CPU > 85% |
| 2 | `"yellow"` | Temp > 70°C |
| 2 | `"yellow"` | Disk > 75% |
| default | `"green"` | All clear |

The first matching rule wins (red beats yellow beats green). When color changes, emit `health_changed`. Emit on every update (not just on change) so newly-connected widgets get the current state immediately.

**Initial state:** `_firestore_ok = True`, `_camera_ok = True` — optimistic until first signal arrives.

**Slots:**
- `on_cpu(value: float)`
- `on_temp(value: float)`
- `on_disk(value: float)`
- `on_throttle(bitmask: int)`
- `on_camera_ok(ok: bool)`
- `on_firestore_ok(ok: bool)`

---

### AppBus additions (`core/bus.py`)

```python
firestore_ok_changed = pyqtSignal(bool)   # True = last write succeeded
camera_ok_changed    = pyqtSignal(bool)   # True = ≥1 camera probed OK
```

---

### Reporter changes (`core/reporter.py`)

After each heartbeat Firestore write (success or exception), emit:
```python
bus.firestore_ok_changed.emit(True)   # on success
bus.firestore_ok_changed.emit(False)  # on exception
```

Only the `_heartbeat` method needs updating; transaction writes are best-effort and don't drive the connectivity indicator.

---

### UI: `StatusDotButton(QPushButton)` — in `ui/header.py`

Subclass of QPushButton. `paintEvent` calls `super().paintEvent(event)` then overlays a 12 px filled circle in the top-right corner with a 2 px dark ring for contrast on the active green background.

```
Colors:
  "green"  → #39ff14
  "yellow" → #f0a000
  "red"    → #ff2244
  None     → dot hidden (initial state)
```

**Public method:** `set_health(color: str)` — updates dot color, calls `self.update()`.

The System tab button in `HeaderWidget` becomes a `StatusDotButton`. The Dashboard tab button remains a plain `QPushButton`.

`HeaderWidget` gains a slot `update_system_health(color: str, reason: str)` that calls `self._tab_buttons["system"].set_health(color)`.

---

### UI: Status row in `SystemScreen` (`ui/screens/system.py`)

A `QLabel` inserted as the first widget in the root `QVBoxLayout`, above `cpu_graph`.

- Fixed height: 22 px
- Left-aligned, `font-size: 10pt`
- Initial text: `"● Waiting…"` in dim color

Slot `update_health(color: str, reason: str)` updates text and color:

| color | symbol | text color |
|-------|--------|------------|
| `"green"` | `●` | `#39ff14` |
| `"yellow"` | `⚠` | `#f0a000` |
| `"red"` | `✕` | `#ff2244` |

---

### Wiring in `main.py`

After `DataSampler` and `Reporter` are set up:

```python
from core.health import HealthMonitor

self._health = HealthMonitor(self)
self._sampler.cpu_sample.connect(self._health.on_cpu)
self._sampler.temp_sample.connect(self._health.on_temp)
self._sampler.disk_sample.connect(self._health.on_disk)
self._sampler.throttle_sample.connect(self._health.on_throttle)
bus.camera_ok_changed.connect(self._health.on_camera_ok)
bus.firestore_ok_changed.connect(self._health.on_firestore_ok)
self._health.health_changed.connect(self._header.update_system_health)
self._health.health_changed.connect(self._system.update_health)
```

Camera status emitted once after probe (already in main.py before MainWindow):
```python
registry.probe()
bus.camera_ok_changed.emit(len(registry.cameras()) > 0)
```

Note: `bus.camera_ok_changed` must be emitted before MainWindow connects to it, so emit it from within `MainWindow.__init__` after header/health setup, using the already-probed `registry`.

---

## Files Modified

| File | Change |
|------|--------|
| `ui/theme.py` | `font-size: 15pt` → `13pt` in BTN_ACTIVE and BTN_INACTIVE |
| `core/bus.py` | Add `firestore_ok_changed`, `camera_ok_changed` signals |
| `core/health.py` | New file — `HealthMonitor` class |
| `core/reporter.py` | Emit `bus.firestore_ok_changed` on heartbeat success/failure |
| `ui/header.py` | Add `StatusDotButton`; System tab uses it; add `update_system_health` slot |
| `ui/screens/system.py` | Add status label row; add `update_health` slot |
| `main.py` | Create `HealthMonitor`, wire signals, emit initial camera status |

---

## Out of Scope

- Dynamic baseline tracking for CPU/temp (fixed thresholds only)
- Per-camera individual health tracking (binary: any camera OK or not)
- Connectivity probe independent of Firestore (Reporter failure is the proxy)
- Clicking the dot to navigate to System screen (tab button click already does this)
