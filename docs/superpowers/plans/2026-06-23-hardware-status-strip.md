# Hardware Status Strip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 60px hardware status strip to the System screen showing throttle status, fan level, and disk usage.

**Architecture:** `DataSampler` gets three new signals backed by private helper methods (for testability). A new `HardwareStatusBar` widget holds three QPainter panels in an `QHBoxLayout`. `SystemScreen.wire_sampler()` connects the new signals to the bar.

**Tech Stack:** PyQt5, psutil (already a dependency), subprocess (stdlib), sysfs reads

## Global Constraints

- Python 3 / PyQt5 — no new pip dependencies
- All panel drawing via `paintEvent` + `QPainter` only; no Qt layout children inside painted regions
- Status strip is display-only — no touch interaction; 60px fixed height is acceptable (not a touch target)
- Graceful fallback when running on non-RPi hardware: `vcgencmd` absent → throttle = 0 (OK); fan sysfs absent → level = -1 (N/A)
- Palette: `PANEL_BG`, `BORDER_DIM`, `ACCENT_GREEN`, `TEXT_MID`, `TEXT_DIM` from `ui/theme.py`; amber = `QColor("#f0a000")` inline; red = `QColor("#ff2244")` inline
- Tests: pytest + pytest-qt; run with `python3 -m pytest tests/ -v`
- Test files must include the sys.path boilerplate at the top (see existing tests for pattern)

---

### Task 1: Extend DataSampler with fan, disk, and throttle signals

**Files:**
- Modify: `core/sampler.py`
- Create: `tests/test_sampler.py`

**Interfaces:**
- Produces:
  - `DataSampler.fan_sample: pyqtSignal(int)` — fan level ≥ 0, or -1 if sysfs path absent
  - `DataSampler.disk_sample: pyqtSignal(float)` — disk usage percent 0.0–100.0
  - `DataSampler.throttle_sample: pyqtSignal(int)` — raw vcgencmd bitmask; 0 if vcgencmd absent or times out
  - `DataSampler._read_fan() -> int`
  - `DataSampler._read_disk() -> float`
  - `DataSampler._read_throttle() -> int`

- [ ] **Step 1: Write failing tests**

Create `tests/test_sampler.py`:

```python
import os
import subprocess
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, mock_open, MagicMock
import pytest
from core.sampler import DataSampler


class TestNewSignalsEmitted:
    def test_fan_signal_emitted(self, qtbot):
        sampler = DataSampler()
        received = []
        sampler.fan_sample.connect(received.append)
        with patch.object(sampler, '_read_fan', return_value=3), \
             patch.object(sampler, '_read_disk', return_value=45.0), \
             patch.object(sampler, '_read_throttle', return_value=0), \
             patch('psutil.cpu_percent', return_value=10.0), \
             patch('psutil.sensors_temperatures',
                   return_value={'cpu_thermal': [MagicMock(current=55.0)]}):
            sampler._sample()
        assert received == [3]

    def test_disk_signal_emitted(self, qtbot):
        sampler = DataSampler()
        received = []
        sampler.disk_sample.connect(received.append)
        with patch.object(sampler, '_read_fan', return_value=-1), \
             patch.object(sampler, '_read_disk', return_value=72.5), \
             patch.object(sampler, '_read_throttle', return_value=0), \
             patch('psutil.cpu_percent', return_value=10.0), \
             patch('psutil.sensors_temperatures',
                   return_value={'cpu_thermal': [MagicMock(current=55.0)]}):
            sampler._sample()
        assert received == [pytest.approx(72.5)]

    def test_throttle_signal_emitted(self, qtbot):
        sampler = DataSampler()
        received = []
        sampler.throttle_sample.connect(received.append)
        with patch.object(sampler, '_read_fan', return_value=0), \
             patch.object(sampler, '_read_disk', return_value=50.0), \
             patch.object(sampler, '_read_throttle', return_value=0x50005), \
             patch('psutil.cpu_percent', return_value=10.0), \
             patch('psutil.sensors_temperatures',
                   return_value={'cpu_thermal': [MagicMock(current=55.0)]}):
            sampler._sample()
        assert received == [0x50005]


class TestReadFan:
    def test_returns_integer_from_sysfs(self):
        sampler = DataSampler()
        with patch('builtins.open', mock_open(read_data='4\n')):
            assert sampler._read_fan() == 4

    def test_strips_whitespace(self):
        sampler = DataSampler()
        with patch('builtins.open', mock_open(read_data='  2  \n')):
            assert sampler._read_fan() == 2

    def test_returns_minus_one_on_oserror(self):
        sampler = DataSampler()
        with patch('builtins.open', side_effect=OSError):
            assert sampler._read_fan() == -1

    def test_returns_minus_one_on_valueerror(self):
        sampler = DataSampler()
        with patch('builtins.open', mock_open(read_data='not-a-number\n')):
            assert sampler._read_fan() == -1


class TestReadDisk:
    def test_returns_usage_percent(self):
        sampler = DataSampler()
        mock_usage = MagicMock()
        mock_usage.percent = 38.2
        with patch('psutil.disk_usage', return_value=mock_usage):
            assert sampler._read_disk() == pytest.approx(38.2)

    def test_returns_zero_on_oserror(self):
        sampler = DataSampler()
        with patch('psutil.disk_usage', side_effect=OSError):
            assert sampler._read_disk() == 0.0


class TestReadThrottle:
    def test_parses_vcgencmd_output(self):
        sampler = DataSampler()
        mock_result = MagicMock()
        mock_result.stdout = b'throttled=0x50005\n'
        with patch('subprocess.run', return_value=mock_result):
            assert sampler._read_throttle() == 0x50005

    def test_parses_zero_ok_output(self):
        sampler = DataSampler()
        mock_result = MagicMock()
        mock_result.stdout = b'throttled=0x0\n'
        with patch('subprocess.run', return_value=mock_result):
            assert sampler._read_throttle() == 0

    def test_returns_zero_when_vcgencmd_missing(self):
        sampler = DataSampler()
        with patch('subprocess.run', side_effect=FileNotFoundError):
            assert sampler._read_throttle() == 0

    def test_returns_zero_on_timeout(self):
        sampler = DataSampler()
        with patch('subprocess.run',
                   side_effect=subprocess.TimeoutExpired('vcgencmd', 1)):
            assert sampler._read_throttle() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_sampler.py -v
```

Expected: FAIL — `DataSampler` has no `fan_sample`, `disk_sample`, `throttle_sample`, `_read_fan`, `_read_disk`, or `_read_throttle`.

- [ ] **Step 3: Implement the changes**

Replace `core/sampler.py` entirely:

```python
import subprocess
import psutil
from PyQt5.QtCore import QObject, QTimer, pyqtSignal


class DataSampler(QObject):
    cpu_sample      = pyqtSignal(float)
    temp_sample     = pyqtSignal(float)
    fan_sample      = pyqtSignal(int)
    disk_sample     = pyqtSignal(float)
    throttle_sample = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        psutil.cpu_percent(interval=None)  # warm up
        self.timer = QTimer()
        self.timer.setInterval(2000)       # fixed 2 s base rate
        self.timer.timeout.connect(self._sample)

    def start(self):
        self.timer.start()

    def stop(self):
        self.timer.stop()

    def _sample(self):
        cpu = psutil.cpu_percent(interval=None)
        temps = psutil.sensors_temperatures()
        try:
            temp = temps['cpu_thermal'][0].current
        except (KeyError, IndexError, TypeError):
            try:
                with open('/sys/class/thermal/thermal_zone0/temp') as f:
                    temp = int(f.read()) / 1000.0
            except OSError:
                temp = 0.0

        self.cpu_sample.emit(cpu)
        self.temp_sample.emit(temp)
        self.fan_sample.emit(self._read_fan())
        self.disk_sample.emit(self._read_disk())
        self.throttle_sample.emit(self._read_throttle())

    def _read_fan(self):
        try:
            with open('/sys/class/thermal/cooling_device0/cur_state') as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return -1

    def _read_disk(self):
        try:
            return psutil.disk_usage('/').percent
        except OSError:
            return 0.0

    def _read_throttle(self):
        try:
            result = subprocess.run(
                ['vcgencmd', 'get_throttled'],
                capture_output=True, timeout=1,
            )
            return int(result.stdout.decode().split('=')[1].strip(), 16)
        except Exception:
            return 0
```

- [ ] **Step 4: Run new tests to verify they pass**

```bash
python3 -m pytest tests/test_sampler.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add core/sampler.py tests/test_sampler.py
git commit -m "feat: add fan, disk, and throttle signals to DataSampler"
```

---

### Task 2: Create HardwareStatusBar widget

**Files:**
- Create: `ui/widgets/hardware_status.py`
- Create: `tests/test_hardware_status.py`

**Interfaces:**
- Consumes: nothing from Task 1 at import time (signals are wired later in Task 3)
- Produces:
  - `HardwareStatusBar(QWidget)` with:
    - `push_throttle(bitmask: int) -> None`
    - `push_fan(level: int) -> None`  — pass -1 to show "N/A"
    - `push_disk(percent: float) -> None`

- [ ] **Step 1: Write failing smoke tests**

Create `tests/test_hardware_status.py`:

```python
import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.widgets.hardware_status import HardwareStatusBar


class TestHardwareStatusBarSmoke:
    """Verify the widget renders without crash for all significant states."""

    def test_ok_state(self, qtbot):
        bar = HardwareStatusBar()
        qtbot.addWidget(bar)
        bar.resize(800, 60)
        bar.push_throttle(0)
        bar.push_fan(0)
        bar.push_disk(30.0)
        bar.show()
        bar.repaint()

    def test_all_current_throttle_flags(self, qtbot):
        bar = HardwareStatusBar()
        qtbot.addWidget(bar)
        bar.resize(800, 60)
        bar.push_throttle(0x000F)   # all four current-flag bits set
        bar.push_fan(7)
        bar.push_disk(50.0)
        bar.show()
        bar.repaint()

    def test_boot_only_throttle_flags(self, qtbot):
        bar = HardwareStatusBar()
        qtbot.addWidget(bar)
        bar.resize(800, 60)
        bar.push_throttle(0xF0000)  # only historical bits set
        bar.push_fan(3)
        bar.push_disk(50.0)
        bar.show()
        bar.repaint()

    def test_na_fan(self, qtbot):
        bar = HardwareStatusBar()
        qtbot.addWidget(bar)
        bar.resize(800, 60)
        bar.push_throttle(0)
        bar.push_fan(-1)
        bar.push_disk(50.0)
        bar.show()
        bar.repaint()

    def test_disk_at_zero(self, qtbot):
        bar = HardwareStatusBar()
        qtbot.addWidget(bar)
        bar.resize(800, 60)
        bar.push_throttle(0)
        bar.push_fan(2)
        bar.push_disk(0.0)
        bar.show()
        bar.repaint()

    def test_disk_at_100(self, qtbot):
        bar = HardwareStatusBar()
        qtbot.addWidget(bar)
        bar.resize(800, 60)
        bar.push_throttle(0)
        bar.push_fan(2)
        bar.push_disk(100.0)
        bar.show()
        bar.repaint()

    def test_disk_amber_threshold(self, qtbot):
        """75% disk should render in amber."""
        bar = HardwareStatusBar()
        qtbot.addWidget(bar)
        bar.resize(800, 60)
        bar.push_throttle(0)
        bar.push_fan(1)
        bar.push_disk(75.0)
        bar.show()
        bar.repaint()

    def test_disk_red_threshold(self, qtbot):
        """90% disk should render in red."""
        bar = HardwareStatusBar()
        qtbot.addWidget(bar)
        bar.resize(800, 60)
        bar.push_throttle(0)
        bar.push_fan(1)
        bar.push_disk(90.0)
        bar.show()
        bar.repaint()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_hardware_status.py -v
```

Expected: FAIL — `ui.widgets.hardware_status` module does not exist.

- [ ] **Step 3: Implement the widget**

Create `ui/widgets/hardware_status.py`:

```python
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QPen, QColor, QFont
from PyQt5.QtWidgets import QWidget, QHBoxLayout

from ui.theme import PANEL_BG, BORDER_DIM, TEXT_MID, TEXT_DIM, ACCENT_GREEN

_AMBER = QColor("#f0a000")
_RED   = QColor("#ff2244")

# (bit-index, display-label, color) for bits that reflect *current* state
_CURRENT_FLAGS = [
    (0, "UV!",  _RED),
    (1, "CAP",  _AMBER),
    (2, "HOT!", _RED),
    (3, "WARM", _AMBER),
]

# (bit-index, display-label) for bits that reflect *historical* (since-boot) state
_BOOT_FLAGS = [
    (16, "UV"),
    (17, "CAP"),
    (18, "HOT"),
    (19, "WARM"),
]

_FAN_MAX = 7   # RPi 5 official active cooler: cur_state range 0–7


class _ThrottlePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bitmask = 0

    def update_value(self, bitmask):
        self._bitmask = bitmask
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, PANEL_BG)
        painter.fillRect(0, 0, 3, h, BORDER_DIM)
        painter.setPen(QPen(BORDER_DIM, 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        pad = 8

        painter.setFont(QFont("DejaVu Sans", 8))
        painter.setPen(QPen(TEXT_MID))
        painter.drawText(pad + 4, 4, w - pad * 2, 14,
                         Qt.AlignLeft | Qt.AlignTop, "THROTTLE")

        current_active = [(label, color)
                          for bit, label, color in _CURRENT_FLAGS
                          if self._bitmask & (1 << bit)]
        boot_active    = [label
                          for bit, label in _BOOT_FLAGS
                          if self._bitmask & (1 << bit)]

        if not current_active:
            painter.setFont(QFont("DejaVu Sans", 13, QFont.Bold))
            painter.setPen(QPen(ACCENT_GREEN))
            painter.drawText(pad, 18, w - pad * 2, 24,
                             Qt.AlignLeft | Qt.AlignVCenter, "● OK")
        else:
            status_text = "⚠ " + "  ".join(label for label, _ in current_active)
            _, color = current_active[0]
            painter.setFont(QFont("DejaVu Sans", 13, QFont.Bold))
            painter.setPen(QPen(color))
            painter.drawText(pad, 18, w - pad * 2, 22,
                             Qt.AlignLeft | Qt.AlignVCenter, status_text)

        if boot_active:
            painter.setFont(QFont("DejaVu Sans", 7))
            painter.setPen(QPen(TEXT_DIM))
            painter.drawText(pad + 4, 42, w - pad * 2, 14,
                             Qt.AlignLeft | Qt.AlignTop,
                             "boot: " + " ".join(boot_active))

        painter.end()


class _FanPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = -1

    def update_value(self, level):
        self._level = level
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, PANEL_BG)
        painter.fillRect(0, 0, 3, h, BORDER_DIM)
        painter.setPen(QPen(BORDER_DIM, 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        pad = 8

        painter.setFont(QFont("DejaVu Sans", 8))
        painter.setPen(QPen(TEXT_MID))
        painter.drawText(pad + 4, 4, w - pad * 2, 14,
                         Qt.AlignLeft | Qt.AlignTop, "FAN")

        if self._level < 0:
            painter.setFont(QFont("DejaVu Sans", 11))
            painter.setPen(QPen(TEXT_DIM))
            painter.drawText(pad, 18, w - pad * 2, 24,
                             Qt.AlignLeft | Qt.AlignVCenter, "N/A")
        else:
            painter.setFont(QFont("DejaVu Sans", 13, QFont.Bold))
            painter.setPen(QPen(ACCENT_GREEN))
            painter.drawText(pad, 18, w - pad * 2, 22,
                             Qt.AlignLeft | Qt.AlignVCenter,
                             f"Level {self._level}/{_FAN_MAX}")

            bar_x, bar_y = pad + 4, 42
            bar_w = w - pad * 2 - 8
            bar_h = 10
            ratio = max(0.0, min(1.0, self._level / _FAN_MAX))

            bg = QColor(ACCENT_GREEN)
            bg.setAlpha(25)
            painter.setBrush(bg)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 4, 4)

            if ratio > 0:
                fill = QColor(ACCENT_GREEN)
                fill.setAlpha(200)
                painter.setBrush(fill)
                painter.drawRoundedRect(bar_x, bar_y, int(bar_w * ratio), bar_h, 4, 4)

        painter.end()


class _DiskPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._percent = 0.0

    def update_value(self, percent):
        self._percent = percent
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, PANEL_BG)
        painter.fillRect(0, 0, 3, h, BORDER_DIM)
        painter.setPen(QPen(BORDER_DIM, 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        pad = 8
        color = (_RED   if self._percent >= 90 else
                 _AMBER if self._percent >= 75 else
                 ACCENT_GREEN)

        painter.setFont(QFont("DejaVu Sans", 8))
        painter.setPen(QPen(TEXT_MID))
        painter.drawText(pad + 4, 4, w - pad * 2, 14,
                         Qt.AlignLeft | Qt.AlignTop, "DISK")

        painter.setFont(QFont("DejaVu Sans", 13, QFont.Bold))
        painter.setPen(QPen(color))
        painter.drawText(pad, 18, w - pad * 2, 22,
                         Qt.AlignLeft | Qt.AlignVCenter,
                         f"{self._percent:.1f}%")

        bar_x, bar_y = pad + 4, 42
        bar_w = w - pad * 2 - 8
        bar_h = 10
        ratio = max(0.0, min(1.0, self._percent / 100.0))

        bg = QColor(color)
        bg.setAlpha(25)
        painter.setBrush(bg)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 4, 4)

        if ratio > 0:
            fill = QColor(color)
            fill.setAlpha(200)
            painter.setBrush(fill)
            painter.drawRoundedRect(bar_x, bar_y, int(bar_w * ratio), bar_h, 4, 4)

        painter.end()


class HardwareStatusBar(QWidget):
    """Three-panel status strip: throttle flags | fan level | disk usage."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._throttle = _ThrottlePanel()
        self._fan      = _FanPanel()
        self._disk     = _DiskPanel()

        layout.addWidget(self._throttle, stretch=1)
        layout.addWidget(self._fan,      stretch=1)
        layout.addWidget(self._disk,     stretch=1)

    def push_throttle(self, bitmask: int):
        self._throttle.update_value(bitmask)

    def push_fan(self, level: int):
        self._fan.update_value(level)

    def push_disk(self, percent: float):
        self._disk.update_value(percent)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_hardware_status.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add ui/widgets/hardware_status.py tests/test_hardware_status.py
git commit -m "feat: add HardwareStatusBar widget for throttle, fan, and disk"
```

---

### Task 3: Wire HardwareStatusBar into SystemScreen

**Files:**
- Modify: `ui/screens/system.py`

**Interfaces:**
- Consumes:
  - `HardwareStatusBar` from `ui/widgets/hardware_status` (Task 2): `push_fan(int)`, `push_disk(float)`, `push_throttle(int)`
  - `DataSampler.fan_sample`, `.disk_sample`, `.throttle_sample` signals (Task 1)
- The existing `wire_sampler(sampler)` public method is extended; signature unchanged

- [ ] **Step 1: Replace `ui/screens/system.py`**

```python
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton

from ui.theme import ACCENT_GREEN, WINDOWS, BTN_ACTIVE, BTN_INACTIVE
from ui.widgets.graph import GraphWidget
from ui.widgets.hardware_status import HardwareStatusBar

_DEFAULT_WINDOW = "5 min"


class SystemScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_window = _DEFAULT_WINDOW

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(8)

        self.cpu_graph = GraphWidget(
            "CPU Usage", "%", ACCENT_GREEN,
            min_span=20, anchor_zero=True,
        )
        # Temperature: cold colour used for area fill; line segments are
        # heat-mapped green → amber → red via _temp_color().
        self.temp_graph = GraphWidget(
            "CPU Temperature", "°C", QColor("#39ff14"),
            min_span=20, heat_color=True,
        )
        root.addWidget(self.cpu_graph, stretch=1)
        root.addWidget(self.temp_graph, stretch=1)

        self.hw_status = HardwareStatusBar()
        self.hw_status.setFixedHeight(60)
        root.addWidget(self.hw_status)

        # Time-window button bar
        bar = QWidget()
        bar.setFixedHeight(70)
        bar.setStyleSheet("background-color: #0a0a0a; border-top: 2px solid #1a5c08;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(12)

        self._window_buttons = {}
        for label, _ in WINDOWS:
            btn = QPushButton(label)
            btn.setFixedHeight(52)
            btn.setMinimumWidth(90)
            btn.clicked.connect(lambda _, l=label: self._select_window(l))
            bl.addWidget(btn)
            self._window_buttons[label] = btn

        root.addWidget(bar)
        self._apply_styles(_DEFAULT_WINDOW)

    def wire_sampler(self, sampler):
        """Connect DataSampler signals. Called by MainWindow after construction."""
        sampler.cpu_sample.connect(self.cpu_graph.push)
        sampler.temp_sample.connect(self.temp_graph.push)
        sampler.fan_sample.connect(self.hw_status.push_fan)
        sampler.disk_sample.connect(self.hw_status.push_disk)
        sampler.throttle_sample.connect(self.hw_status.push_throttle)

    def _select_window(self, label):
        if label == self._active_window:
            return
        self._active_window = label
        self._apply_styles(label)
        n = dict(WINDOWS)[label]
        self.cpu_graph.set_window(n)
        self.temp_graph.set_window(n)

    def _apply_styles(self, active):
        for label, btn in self._window_buttons.items():
            btn.setStyleSheet(BTN_ACTIVE if label == active else BTN_INACTIVE)
```

- [ ] **Step 2: Run full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add ui/screens/system.py
git commit -m "feat: wire hardware status strip into SystemScreen"
```

---

### Task 4: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

In `README.md`:

1. In the **Current Status** table, add a row for the hardware status strip marked ✅.
2. In the **Architecture** or **File map** section, add `ui/widgets/hardware_status.py` with description `HardwareStatusBar — throttle/fan/disk status strip on System screen`.
3. In the `core/sampler.py` description, note the three new signals: `fan_sample`, `disk_sample`, `throttle_sample`.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README for hardware status strip"
```

---

## Self-Review

**Spec coverage:**
- ✅ Throttle: `vcgencmd get_throttled` → bitmask decode → colored flags
- ✅ Fan: `/sys/class/thermal/cooling_device0/cur_state` → level bar
- ✅ Disk: `psutil.disk_usage('/').percent` → percent bar with color thresholds
- ✅ 60px strip between graphs and button bar
- ✅ Graceful fallbacks on non-RPi hardware
- ✅ Existing palette colors only
- ✅ Tests for all three sampler helpers and edge cases
- ✅ Widget smoke tests covering OK / warning / N/A / boundary states
- ✅ Dashboard `SystemMiniPanel` unchanged

**Placeholder scan:** No TBD/TODO present. All code steps are complete.

**Type consistency:**
- `fan_sample(int)` → `push_fan(int)` → `_FanPanel.update_value(int)` ✅
- `disk_sample(float)` → `push_disk(float)` → `_DiskPanel.update_value(float)` ✅
- `throttle_sample(int)` → `push_throttle(int)` → `_ThrottlePanel.update_value(int)` ✅
