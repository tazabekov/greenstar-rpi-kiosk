# Health Status Indicator & Tab Font Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Shrink the "Dashboard" tab button font and add a green/yellow/red health dot on the System tab button (visible from any screen), backed by a `HealthMonitor` that aggregates CPU, temperature, disk, throttle, camera, and Firestore connectivity signals.

**Architecture:** A new `HealthMonitor(QObject)` in `core/health.py` subscribes to `DataSampler` signals and two new `AppBus` signals (`firestore_ok_changed`, `camera_ok_changed`), evaluates priority-ordered rules, and emits `health_changed(color, reason)`. The `HeaderWidget`'s System tab button becomes a `StatusDotButton` subclass that paints a colored dot overlay. The `SystemScreen` gains a one-line status label at the top.

**Tech Stack:** Python 3, PyQt5, pytest, pytest-qt

## Global Constraints

- All widget tests must set `os.environ.setdefault("DISPLAY", ":0")` before any Qt imports
- Run the full test suite with: `python3 -m pytest tests/ -v` from the project root
- No new dependencies — only stdlib and packages already installed
- Touch-target minimum: ≥ 44 px height for any interactive element
- The singleton `bus` from `core.bus` is used for cross-component signals; tests that touch it must connect and disconnect within the test to avoid leakage

---

### Task 1: Tab Font Fix + New AppBus Signals

**Files:**
- Modify: `ui/theme.py`
- Modify: `core/bus.py`
- Modify: `tests/test_bus.py`

**Interfaces:**
- Produces:
  - `bus.firestore_ok_changed: pyqtSignal(bool)` — True = last Firestore heartbeat succeeded
  - `bus.camera_ok_changed: pyqtSignal(bool)` — True = ≥ 1 camera probed OK at startup

- [ ] **Step 1: Write the failing tests for the new bus signals** — append to `tests/test_bus.py`:

```python
class TestFirestoreOkChangedSignal:
    def test_fires_true(self, qtbot):
        local_bus = AppBus()
        with qtbot.waitSignal(local_bus.firestore_ok_changed, timeout=1000) as blocker:
            local_bus.firestore_ok_changed.emit(True)
        assert blocker.args[0] is True

    def test_fires_false(self, qtbot):
        local_bus = AppBus()
        with qtbot.waitSignal(local_bus.firestore_ok_changed, timeout=1000) as blocker:
            local_bus.firestore_ok_changed.emit(False)
        assert blocker.args[0] is False


class TestCameraOkChangedSignal:
    def test_fires_true(self, qtbot):
        local_bus = AppBus()
        with qtbot.waitSignal(local_bus.camera_ok_changed, timeout=1000) as blocker:
            local_bus.camera_ok_changed.emit(True)
        assert blocker.args[0] is True

    def test_fires_false(self, qtbot):
        local_bus = AppBus()
        with qtbot.waitSignal(local_bus.camera_ok_changed, timeout=1000) as blocker:
            local_bus.camera_ok_changed.emit(False)
        assert blocker.args[0] is False
```

- [ ] **Step 2: Run tests — expect 4 failures**

```bash
python3 -m pytest tests/test_bus.py::TestFirestoreOkChangedSignal tests/test_bus.py::TestCameraOkChangedSignal -v
```

Expected: 4 failures — `AttributeError: type object 'AppBus' has no attribute 'firestore_ok_changed'`

- [ ] **Step 3: Add the two new signals to `core/bus.py`**

Replace the entire file:

```python
from PyQt5.QtCore import QObject, pyqtSignal


class AppBus(QObject):
    transaction_added          = pyqtSignal(object)           # Transaction
    transaction_event          = pyqtSignal(str, object)      # tx_id, TransactionEvent
    payment_requested          = pyqtSignal(str, float, str)  # tx_id, amount, payment_type
    payment_result             = pyqtSignal(str, bool, str)   # tx_id, success, message
    settings_changed           = pyqtSignal(str, str, str)    # name, location, kiosk_id
    snapshot_interval_changed  = pyqtSignal(int)              # minutes; 0 = disabled
    firestore_ok_changed       = pyqtSignal(bool)             # True = last heartbeat succeeded
    camera_ok_changed          = pyqtSignal(bool)             # True = ≥1 camera probed OK


bus = AppBus()
```

- [ ] **Step 4: Fix the tab font in `ui/theme.py`** — change `font-size: 15pt` to `font-size: 13pt` in both `BTN_ACTIVE` and `BTN_INACTIVE`:

```python
BTN_ACTIVE = (
    "QPushButton { background-color: #39ff14; color: #0d0d0d;"
    " border: 2px solid #39ff14; border-radius: 8px;"
    " font-size: 13pt; font-weight: bold; padding: 6px 0px; }"
)
BTN_INACTIVE = (
    "QPushButton { background-color: #111111; color: #39ff14;"
    " border: 2px solid #1a5c08; border-radius: 8px;"
    " font-size: 13pt; font-weight: bold; padding: 6px 0px; }"
    " QPushButton:hover { border-color: #39ff14; background-color: #0d1f08; }"
)
```

- [ ] **Step 5: Run the new bus signal tests — expect all 4 to pass**

```bash
python3 -m pytest tests/test_bus.py -v
```

Expected: all tests pass (new 4 + existing)

- [ ] **Step 6: Commit**

```bash
git add ui/theme.py core/bus.py tests/test_bus.py
git commit -m "feat: shrink tab font to 13pt and add firestore/camera health signals to AppBus"
```

---

### Task 2: HealthMonitor

**Files:**
- Create: `core/health.py`
- Create: `tests/test_health.py`

**Interfaces:**
- Consumes:
  - `DataSampler.cpu_sample(float)`, `temp_sample(float)`, `disk_sample(float)`, `throttle_sample(int)`
  - `bus.camera_ok_changed(bool)`, `bus.firestore_ok_changed(bool)` — from Task 1
- Produces:
  - `HealthMonitor.health_changed: pyqtSignal(str, str)` — (color, reason) where color ∈ {"green", "yellow", "red"}
  - Slots: `on_cpu(float)`, `on_temp(float)`, `on_disk(float)`, `on_throttle(int)`, `on_camera_ok(bool)`, `on_firestore_ok(bool)`
  - Thresholds: CPU ≥ 85.0 → yellow, Temp ≥ 70.0 → yellow, Disk ≥ 75.0 → yellow
  - Priority: red (firestore) > yellow (camera, throttle, cpu, temp, disk) > green

- [ ] **Step 1: Write the failing tests** — create `tests/test_health.py`:

```python
import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from core.health import HealthMonitor


def _collect(monitor, qtbot):
    """Helper: return list to capture health_changed emissions."""
    received = []
    monitor.health_changed.connect(lambda c, r: received.append((c, r)))
    return received


class TestHealthMonitorGreen:
    def test_default_all_clear_after_first_update(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(0.0)
        assert received[-1][0] == "green"

    def test_cpu_below_threshold_is_green(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(84.9)
        assert received[-1][0] == "green"

    def test_temp_below_threshold_is_green(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_temp(69.9)
        assert received[-1][0] == "green"

    def test_disk_below_threshold_is_green(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_disk(74.9)
        assert received[-1][0] == "green"

    def test_throttle_boot_only_flags_is_green(self, qtbot):
        """Bits 16-19 are historical-only; no current throttle → green."""
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_throttle(0xF0000)
        assert received[-1][0] == "green"

    def test_reason_is_all_systems_ok_when_green(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(10.0)
        assert "OK" in received[-1][1] or "ok" in received[-1][1].lower()


class TestHealthMonitorYellow:
    def test_cpu_at_threshold_is_yellow(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(85.0)
        assert received[-1][0] == "yellow"

    def test_cpu_above_threshold_is_yellow(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(90.0)
        assert received[-1][0] == "yellow"

    def test_temp_at_threshold_is_yellow(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_temp(70.0)
        assert received[-1][0] == "yellow"

    def test_disk_at_threshold_is_yellow(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_disk(75.0)
        assert received[-1][0] == "yellow"

    def test_throttle_current_flags_is_yellow(self, qtbot):
        """Bits 0-3 are current throttle flags."""
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_throttle(0x000F)
        assert received[-1][0] == "yellow"

    def test_throttle_single_current_flag_is_yellow(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_throttle(0x0001)
        assert received[-1][0] == "yellow"

    def test_camera_offline_is_yellow(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_camera_ok(False)
        assert received[-1][0] == "yellow"

    def test_camera_online_is_green(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_camera_ok(True)
        assert received[-1][0] == "green"

    def test_reason_contains_cpu_value(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(90.0)
        assert "90" in received[-1][1]

    def test_reason_contains_temp_value(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_temp(72.0)
        assert "72" in received[-1][1]

    def test_reason_contains_disk_value(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_disk(80.0)
        assert "80" in received[-1][1]


class TestHealthMonitorRed:
    def test_firestore_failure_is_red(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_firestore_ok(False)
        assert received[-1][0] == "red"

    def test_firestore_recovery_returns_to_green(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_firestore_ok(False)
        monitor.on_firestore_ok(True)
        assert received[-1][0] == "green"

    def test_red_overrides_yellow(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(90.0)        # would be yellow
        monitor.on_firestore_ok(False)
        assert received[-1][0] == "red"

    def test_reason_mentions_firestore(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_firestore_ok(False)
        assert "firestore" in received[-1][1].lower() or "write" in received[-1][1].lower()


class TestHealthMonitorEmissionBehavior:
    def test_emits_on_every_slot_call(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(10.0)
        monitor.on_cpu(11.0)
        assert len(received) >= 2

    def test_all_slots_trigger_emission(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(0.0)
        monitor.on_temp(0.0)
        monitor.on_disk(0.0)
        monitor.on_throttle(0)
        monitor.on_camera_ok(True)
        monitor.on_firestore_ok(True)
        assert len(received) == 6
```

- [ ] **Step 2: Run tests — expect failures**

```bash
python3 -m pytest tests/test_health.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.health'`

- [ ] **Step 3: Create `core/health.py`**

```python
from PyQt5.QtCore import QObject, pyqtSignal

_CPU_WARN  = 85.0
_TEMP_WARN = 70.0
_DISK_WARN = 75.0


class HealthMonitor(QObject):
    health_changed = pyqtSignal(str, str)  # color, reason

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cpu          = 0.0
        self._temp         = 0.0
        self._disk         = 0.0
        self._throttle     = 0
        self._camera_ok    = True
        self._firestore_ok = True

    def on_cpu(self, value: float):
        self._cpu = value
        self._evaluate()

    def on_temp(self, value: float):
        self._temp = value
        self._evaluate()

    def on_disk(self, value: float):
        self._disk = value
        self._evaluate()

    def on_throttle(self, bitmask: int):
        self._throttle = bitmask
        self._evaluate()

    def on_camera_ok(self, ok: bool):
        self._camera_ok = ok
        self._evaluate()

    def on_firestore_ok(self, ok: bool):
        self._firestore_ok = ok
        self._evaluate()

    def _evaluate(self):
        if not self._firestore_ok:
            color, reason = "red", "Firestore write failed"
        elif not self._camera_ok:
            color, reason = "yellow", "Camera offline"
        elif self._throttle & 0xF:
            color, reason = "yellow", "CPU throttled"
        elif self._cpu >= _CPU_WARN:
            color, reason = "yellow", f"CPU {self._cpu:.0f}%"
        elif self._temp >= _TEMP_WARN:
            color, reason = "yellow", f"Temp {self._temp:.0f}°C"
        elif self._disk >= _DISK_WARN:
            color, reason = "yellow", f"Disk {self._disk:.0f}%"
        else:
            color, reason = "green", "All systems OK"
        self.health_changed.emit(color, reason)
```

- [ ] **Step 4: Run tests — expect all to pass**

```bash
python3 -m pytest tests/test_health.py -v
```

Expected: all tests pass

- [ ] **Step 5: Run full suite to check for regressions**

```bash
python3 -m pytest tests/ -v
```

Expected: all existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add core/health.py tests/test_health.py
git commit -m "feat: add HealthMonitor with green/yellow/red evaluation logic"
```

---

### Task 3: Reporter Emits `firestore_ok_changed`

**Files:**
- Modify: `core/reporter.py`
- Create: `tests/test_reporter.py`

**Interfaces:**
- Consumes: `bus.firestore_ok_changed: pyqtSignal(bool)` from Task 1
- Produces: `Reporter._heartbeat()` emits `bus.firestore_ok_changed.emit(True)` on success, `bus.firestore_ok_changed.emit(False)` in the except block

- [ ] **Step 1: Write the failing tests** — create `tests/test_reporter.py`:

```python
import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock

import pytest
from core.bus import bus
from core.reporter import Reporter


class TestReporterFirestoreSignal:
    def test_heartbeat_emits_true_on_success(self, qtbot):
        reporter = Reporter()
        mock_ref = MagicMock()
        mock_ref.get.return_value.exists = True
        reporter._kiosk_ref = mock_ref

        received = []
        bus.firestore_ok_changed.connect(received.append)
        try:
            reporter._heartbeat()
            assert True in received
        finally:
            bus.firestore_ok_changed.disconnect(received.append)

    def test_heartbeat_emits_false_on_exception(self, qtbot):
        reporter = Reporter()
        mock_ref = MagicMock()
        mock_ref.get.side_effect = Exception("connection refused")
        reporter._kiosk_ref = mock_ref

        received = []
        bus.firestore_ok_changed.connect(received.append)
        try:
            reporter._heartbeat()
            assert False in received
        finally:
            bus.firestore_ok_changed.disconnect(received.append)

    def test_heartbeat_no_emit_when_kiosk_ref_is_none(self, qtbot):
        reporter = Reporter()
        reporter._kiosk_ref = None

        received = []
        bus.firestore_ok_changed.connect(received.append)
        try:
            reporter._heartbeat()
            assert received == []
        finally:
            bus.firestore_ok_changed.disconnect(received.append)
```

- [ ] **Step 2: Run tests — expect failures**

```bash
python3 -m pytest tests/test_reporter.py -v
```

Expected: `AssertionError` — `True` not in `received` (signal not yet emitted)

- [ ] **Step 3: Modify `core/reporter.py`** — add bus import at the top (after the existing imports):

```python
from core.bus import bus
```

Then modify `_heartbeat` to emit after the try/except. The full `_heartbeat` method becomes:

```python
def _heartbeat(self):
    if not self._kiosk_ref:
        return
    try:
        now = _now_utc()
        snapshot = self._kiosk_ref.get()
        if not snapshot.exists:
            self._kiosk_ref.set({
                "kiosk_id": self._kiosk_id,
                "name": os.getenv("GKM_KIOSK_NAME", self._kiosk_id),
                "location": os.getenv("GKM_KIOSK_LOCATION", ""),
                "registered_at": now,
                "last_heartbeat": now,
                "cpu_percent": self._cpu,
                "temperature_c": self._temp,
            })
            log.info("Reporter: kiosk registered in Firestore")
        else:
            self._kiosk_ref.update({
                "last_heartbeat": now,
                "cpu_percent": self._cpu,
                "temperature_c": self._temp,
                "name": os.getenv("GKM_KIOSK_NAME", self._kiosk_id),
                "location": os.getenv("GKM_KIOSK_LOCATION", ""),
            })

        self._kiosk_ref.collection("metrics").add({
            "cpu_percent": self._cpu,
            "temperature_c": self._temp,
            "recorded_at": now,
        })
        bus.firestore_ok_changed.emit(True)
    except Exception:
        log.exception("Reporter: heartbeat failed — will retry next cycle")
        bus.firestore_ok_changed.emit(False)
```

- [ ] **Step 4: Run tests — expect all to pass**

```bash
python3 -m pytest tests/test_reporter.py -v
```

Expected: all 3 tests pass

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add core/reporter.py tests/test_reporter.py
git commit -m "feat: emit firestore_ok_changed on Reporter heartbeat success and failure"
```

---

### Task 4: StatusDotButton + HeaderWidget Health Slot

**Files:**
- Modify: `ui/header.py`
- Create: `tests/test_header.py`

**Interfaces:**
- Consumes: `HealthMonitor.health_changed(str, str)` from Task 2
- Produces:
  - `StatusDotButton` class (exported from `ui.header`): `set_health(color: str)` — color ∈ {"green", "yellow", "red"}
  - `HeaderWidget.update_system_health(color: str, reason: str)` slot — calls `_tab_buttons["system"].set_health(color)`

- [ ] **Step 1: Write the failing tests** — create `tests/test_header.py`:

```python
import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from ui.header import StatusDotButton, HeaderWidget


class TestStatusDotButton:
    def test_renders_without_dot_initially(self, qtbot):
        btn = StatusDotButton("System")
        qtbot.addWidget(btn)
        btn.resize(120, 44)
        btn.show()
        btn.repaint()

    def test_renders_green_dot(self, qtbot):
        btn = StatusDotButton("System")
        qtbot.addWidget(btn)
        btn.resize(120, 44)
        btn.set_health("green")
        btn.show()
        btn.repaint()

    def test_renders_yellow_dot(self, qtbot):
        btn = StatusDotButton("System")
        qtbot.addWidget(btn)
        btn.resize(120, 44)
        btn.set_health("yellow")
        btn.show()
        btn.repaint()

    def test_renders_red_dot(self, qtbot):
        btn = StatusDotButton("System")
        qtbot.addWidget(btn)
        btn.resize(120, 44)
        btn.set_health("red")
        btn.show()
        btn.repaint()

    def test_unknown_color_hides_dot(self, qtbot):
        btn = StatusDotButton("System")
        qtbot.addWidget(btn)
        btn.resize(120, 44)
        btn.set_health("unknown")
        btn.show()
        btn.repaint()


class TestHeaderWidgetSystemHealth:
    def test_update_system_health_green(self, qtbot):
        header = HeaderWidget()
        qtbot.addWidget(header)
        header.resize(800, 64)
        header.show()
        header.update_system_health("green", "All systems OK")

    def test_update_system_health_yellow(self, qtbot):
        header = HeaderWidget()
        qtbot.addWidget(header)
        header.resize(800, 64)
        header.show()
        header.update_system_health("yellow", "Camera offline")

    def test_update_system_health_red(self, qtbot):
        header = HeaderWidget()
        qtbot.addWidget(header)
        header.resize(800, 64)
        header.show()
        header.update_system_health("red", "Firestore write failed")
```

- [ ] **Step 2: Run tests — expect failures**

```bash
python3 -m pytest tests/test_header.py -v
```

Expected: `ImportError: cannot import name 'StatusDotButton' from 'ui.header'`

- [ ] **Step 3: Modify `ui/header.py`**

Add `pyqtSlot` to the QtCore import line:

```python
from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal, pyqtSlot
```

Insert the `StatusDotButton` class after the `CameraIcon` class (before `HeaderWidget`):

```python
class StatusDotButton(QPushButton):
    """QPushButton that overlays a small health-status dot in the top-right corner."""

    _DOT_R = 6
    _DOT_COLORS = {
        "green":  QColor("#39ff14"),
        "yellow": QColor("#f0a000"),
        "red":    QColor("#ff2244"),
    }

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._dot_color = None

    def set_health(self, color: str):
        self._dot_color = self._DOT_COLORS.get(color)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._dot_color is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._DOT_R
        x = self.width() - r - 5
        y = r + 4
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#0d0d0d"))
        p.drawEllipse(QPointF(x, y), r + 1.5, r + 1.5)
        p.setBrush(self._dot_color)
        p.drawEllipse(QPointF(x, y), float(r), float(r))
        p.end()
```

In `HeaderWidget.__init__`, change the tab button loop so the System tab gets a `StatusDotButton`:

```python
self._tab_buttons = {}
for key, label in self.TABS:
    btn = StatusDotButton(label) if key == "system" else QPushButton(label)
    btn.setFixedHeight(44)
    btn.setMinimumWidth(110)
    btn.clicked.connect(lambda _, k=key: self._on_tab(k))
    layout.addWidget(btn)
    self._tab_buttons[key] = btn
```

Add the `update_system_health` slot to `HeaderWidget` (at the end of the class, after `show_camera_button`):

```python
@pyqtSlot(str, str)
def update_system_health(self, color: str, reason: str):
    self._tab_buttons["system"].set_health(color)
```

- [ ] **Step 4: Run tests — expect all to pass**

```bash
python3 -m pytest tests/test_header.py -v
```

Expected: all 8 tests pass

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add ui/header.py tests/test_header.py
git commit -m "feat: add StatusDotButton and update_system_health slot to HeaderWidget"
```

---

### Task 5: SystemScreen Status Row

**Files:**
- Modify: `ui/screens/system.py`
- Create: `tests/test_system_screen.py`

**Interfaces:**
- Consumes: `HealthMonitor.health_changed(str, str)` from Task 2
- Produces: `SystemScreen.update_health(color: str, reason: str)` slot — updates `_status_label` text and stylesheet

- [ ] **Step 1: Write the failing tests** — create `tests/test_system_screen.py`:

```python
import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from ui.screens.system import SystemScreen


class TestSystemScreenHealthRow:
    def test_renders_initial_waiting_state(self, qtbot):
        screen = SystemScreen()
        qtbot.addWidget(screen)
        screen.resize(800, 416)
        screen.show()
        screen.repaint()

    def test_update_health_green(self, qtbot):
        screen = SystemScreen()
        qtbot.addWidget(screen)
        screen.resize(800, 416)
        screen.update_health("green", "All systems OK")
        screen.show()
        screen.repaint()
        assert "All systems OK" in screen._status_label.text()

    def test_update_health_yellow(self, qtbot):
        screen = SystemScreen()
        qtbot.addWidget(screen)
        screen.resize(800, 416)
        screen.update_health("yellow", "Camera offline")
        screen.show()
        screen.repaint()
        assert "Camera offline" in screen._status_label.text()

    def test_update_health_red(self, qtbot):
        screen = SystemScreen()
        qtbot.addWidget(screen)
        screen.resize(800, 416)
        screen.update_health("red", "Firestore write failed")
        screen.show()
        screen.repaint()
        assert "Firestore write failed" in screen._status_label.text()

    def test_symbol_changes_with_color(self, qtbot):
        screen = SystemScreen()
        qtbot.addWidget(screen)
        screen.resize(800, 416)
        screen.update_health("yellow", "Camera offline")
        assert "⚠" in screen._status_label.text()
        screen.update_health("red", "Firestore write failed")
        assert "✕" in screen._status_label.text()
        screen.update_health("green", "All systems OK")
        assert "●" in screen._status_label.text()
```

- [ ] **Step 2: Run tests — expect failures**

```bash
python3 -m pytest tests/test_system_screen.py -v
```

Expected: `AttributeError: 'SystemScreen' object has no attribute 'update_health'`

- [ ] **Step 3: Modify `ui/screens/system.py`**

Replace the import block at the top:

```python
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from ui.theme import ACCENT_GREEN, WINDOWS, BTN_ACTIVE, BTN_INACTIVE
from ui.widgets.graph import GraphWidget
from ui.widgets.hardware_status import HardwareStatusBar
```

After the existing `_DEFAULT_WINDOW = "5 min"` line, add these two new constants (do not duplicate `_DEFAULT_WINDOW`):

```python
_HEALTH_SYMBOL = {"green": "●", "yellow": "⚠", "red": "✕"}
_HEALTH_STYLE = {
    "green":  "color: #39ff14; font-size: 10pt; padding-left: 4px; border: none;",
    "yellow": "color: #f0a000; font-size: 10pt; padding-left: 4px; border: none;",
    "red":    "color: #ff2244; font-size: 10pt; padding-left: 4px; border: none;",
}
```

In `SystemScreen.__init__`, after the line `root.setSpacing(8)` and **before** `self.cpu_graph = GraphWidget(...)`, insert these four lines:

```python
self._status_label = QLabel("● Waiting…")
self._status_label.setFixedHeight(22)
self._status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
self._status_label.setStyleSheet(
    "color: #555555; font-size: 10pt; padding-left: 4px; border: none;"
)
root.addWidget(self._status_label)
```

The existing `self.cpu_graph = GraphWidget(...)` and everything below it remains unchanged.

Add the `update_health` slot at the end of the class:

```python
@pyqtSlot(str, str)
def update_health(self, color: str, reason: str):
    symbol = _HEALTH_SYMBOL.get(color, "●")
    self._status_label.setText(f"{symbol} {reason}")
    self._status_label.setStyleSheet(
        _HEALTH_STYLE.get(color, _HEALTH_STYLE["green"])
    )
```

- [ ] **Step 4: Run tests — expect all to pass**

```bash
python3 -m pytest tests/test_system_screen.py -v
```

Expected: all 5 tests pass

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add ui/screens/system.py tests/test_system_screen.py
git commit -m "feat: add health status row to SystemScreen with update_health slot"
```

---

### Task 6: Wire Everything in `main.py`

**Files:**
- Modify: `main.py`

**Interfaces:**
- Consumes:
  - `HealthMonitor` from `core.health` (Task 2)
  - `DataSampler.cpu_sample`, `temp_sample`, `disk_sample`, `throttle_sample` (existing)
  - `bus.camera_ok_changed`, `bus.firestore_ok_changed` (Task 1)
  - `HeaderWidget.update_system_health` (Task 4)
  - `SystemScreen.update_health` (Task 5)
  - `registry.cameras()` (existing — already probed before MainWindow starts)
- Produces: fully wired health pipeline; initial camera status emitted once during startup

- [ ] **Step 1: Add the import** to `main.py` — insert after the other `core.*` imports:

```python
from core.health import HealthMonitor
```

- [ ] **Step 2: Wire HealthMonitor in `MainWindow.__init__`** — insert the block immediately after `self._reporter.start()` (line ~144 in current `main.py`):

```python
self._health = HealthMonitor(self)
self._sampler.cpu_sample.connect(self._health.on_cpu)
self._sampler.temp_sample.connect(self._health.on_temp)
self._sampler.disk_sample.connect(self._health.on_disk)
self._sampler.throttle_sample.connect(self._health.on_throttle)
bus.camera_ok_changed.connect(self._health.on_camera_ok)
bus.firestore_ok_changed.connect(self._health.on_firestore_ok)
self._health.health_changed.connect(self._header.update_system_health)
self._health.health_changed.connect(self._system.update_health)

# Emit initial camera status — registry was already probed before MainWindow started
bus.camera_ok_changed.emit(bool(registry.cameras()))
```

- [ ] **Step 3: Verify the app starts without error**

```bash
DISPLAY=:0 python3 main.py &
sleep 3
kill %1
```

Expected: no tracebacks in stderr; the process starts and terminates cleanly

- [ ] **Step 4: Run the full test suite one final time**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: wire HealthMonitor into main.py and emit initial camera status"
```

---

### Task 7: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the Current Status table** — mark "Health status indicator" as ✅ shipped; also update the Architecture or file map section to mention `core/health.py`

- [ ] **Step 2: Add `core/health.py` to the File Map section** with a one-line description:

```
core/health.py       HealthMonitor — aggregates cpu/temp/disk/throttle/camera/firestore signals
                     and emits health_changed("green"|"yellow"|"red", reason)
```

- [ ] **Step 3: Note the two new AppBus signals** in the Architecture section or wherever AppBus is described:

```
firestore_ok_changed(bool)  — emitted by Reporter after each 60 s heartbeat
camera_ok_changed(bool)     — emitted once at startup after registry.probe()
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README for health status indicator feature"
```
