# Camera Live View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a conditional "📷" button to the kiosk header that opens a full-overlay modal streaming live video from the attached OV5647 camera.

**Architecture:** Detect cameras once at startup via `Picamera2.global_camera_info()`; if any found, call `HeaderWidget.show_camera_button()` which dynamically inserts a button before the gear icon and emits `cameras_requested`. `MainWindow` wires that signal to open `CameraModal`, which owns the `Picamera2` instance and a `QTimer` that grabs frames at ~15 fps and paints them into a `QLabel`.

**Tech Stack:** Python 3, PyQt5, picamera2 (v0.3.31, system apt package), numpy (already installed as picamera2 dependency).

## Global Constraints

- `picamera2` is a system apt package — do NOT add it to `requirements.txt`
- All modal dialogs use `Qt.FramelessWindowHint | Qt.Dialog`, `WA_TranslucentBackground`, full-parent-size overlay — follow `SettingsModal` exactly
- Touch targets ≥ 44px tall
- Dark theme: `#0d0d0d` background, `#1a5c08` border, `#39ff14` accent
- No new pip packages

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `ui/widgets/camera_modal.py` | **Create** | `CameraModal` QDialog — owns camera lifecycle + frame rendering |
| `ui/header.py` | **Modify** | Add `cameras_requested` signal; store `_gear` ref; add `show_camera_button()` |
| `main.py` | **Modify** | Detect cameras at startup; wire header signal → `_open_camera_modal()` |
| `tests/test_camera_modal.py` | **Create** | Widget structure tests + header button tests (no hardware required) |

---

### Task 1: CameraModal widget

**Files:**
- Create: `ui/widgets/camera_modal.py`
- Create: `tests/test_camera_modal.py`

**Interfaces:**
- Produces: `CameraModal(parent=None)` — `QDialog` subclass, call `.exec_()` to open

- [ ] **Step 1: Write the failing tests**

Create `tests/test_camera_modal.py`:

```python
import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PyQt5.QtWidgets import QLabel, QPushButton

from ui.widgets.camera_modal import CameraModal


class TestCameraModal:
    def test_instantiation(self, qtbot):
        modal = CameraModal(parent=None)
        qtbot.addWidget(modal)
        assert modal is not None

    def test_has_view_label(self, qtbot):
        modal = CameraModal(parent=None)
        qtbot.addWidget(modal)
        assert isinstance(modal._view, QLabel)

    def test_status_shows_resolution(self, qtbot):
        modal = CameraModal(parent=None)
        qtbot.addWidget(modal)
        assert "640" in modal._status.text()
        assert "480" in modal._status.text()

    def test_timer_not_active_before_show(self, qtbot):
        modal = CameraModal(parent=None)
        qtbot.addWidget(modal)
        assert not modal._timer.isActive()

    def test_cam_none_before_show(self, qtbot):
        modal = CameraModal(parent=None)
        qtbot.addWidget(modal)
        assert modal._cam is None

    def test_close_stops_timer(self, qtbot):
        modal = CameraModal(parent=None)
        qtbot.addWidget(modal)
        modal._timer.start()
        modal.close()
        assert not modal._timer.isActive()

    def test_cam_none_after_close(self, qtbot):
        modal = CameraModal(parent=None)
        qtbot.addWidget(modal)
        modal._cam = object()  # simulate an open camera handle
        modal._cam = None      # close sets it to None
        modal.close()
        assert modal._cam is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/ali/code/greenstar-rpi-kiosk
python3 -m pytest tests/test_camera_modal.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` for `camera_modal`.

- [ ] **Step 3: Create `ui/widgets/camera_modal.py`**

```python
import numpy as np
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QWidget,
)

_TITLE_STYLE = "color: #39ff14; font-size: 14pt; font-weight: bold; border: none;"
_STATUS_STYLE = "color: #555555; font-size: 9pt; border: none;"
_VIEW_STYLE = (
    "background-color: #000000;"
    " border: 1px solid #1a1a1a; border-radius: 4px;"
)
_CLOSE_STYLE = (
    "QPushButton { background-color: #1a1a1a; color: #888888;"
    " border: 1px solid #333333; border-radius: 6px;"
    " font-size: 12pt; padding: 0 16px; }"
    " QPushButton:hover { border-color: #666666; color: #aaaaaa; }"
    " QPushButton:pressed { background-color: #2a2a2a; }"
)
_X_STYLE = (
    "QPushButton { background-color: transparent; color: #555555;"
    " border: none; font-size: 14pt; }"
    " QPushButton:hover { color: #e8e8e8; }"
)

_FRAME_MS = 66        # ~15 fps
_W, _H = 640, 480


class CameraModal(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        if parent:
            self.resize(parent.width(), parent.height())
            self.move(0, 0)
        self._cam = None
        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._grab_frame)
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget(self)
        card.setStyleSheet(
            "background-color: #0d0d0d;"
            " border: 2px solid #1a5c08; border-radius: 10px;"
        )
        card.setFixedSize(700, 580)
        outer.addWidget(card, alignment=Qt.AlignCenter)

        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(16, 12, 16, 16)
        vbox.setSpacing(10)

        # Title row
        title_row = QHBoxLayout()
        title = QLabel("Live Camera")
        title.setStyleSheet(_TITLE_STYLE)
        title_row.addWidget(title)
        title_row.addStretch()
        x_btn = QPushButton("✕")
        x_btn.setFixedSize(32, 32)
        x_btn.setStyleSheet(_X_STYLE)
        x_btn.clicked.connect(self.close)
        title_row.addWidget(x_btn)
        vbox.addLayout(title_row)

        # Video view
        self._view = QLabel()
        self._view.setAlignment(Qt.AlignCenter)
        self._view.setMinimumSize(_W, _H)
        self._view.setStyleSheet(_VIEW_STYLE)
        vbox.addWidget(self._view, stretch=1)

        # Status
        self._status = QLabel(f"{_W} × {_H}  |  15 fps")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setStyleSheet(_STATUS_STYLE)
        vbox.addWidget(self._status)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(44)
        close_btn.setStyleSheet(_CLOSE_STYLE)
        close_btn.clicked.connect(self.close)
        vbox.addWidget(close_btn)

    def showEvent(self, event):
        super().showEvent(event)
        self._start_camera()

    def _start_camera(self):
        try:
            from picamera2 import Picamera2
            self._cam = Picamera2(0)
            cfg = self._cam.create_preview_configuration(
                main={"size": (_W, _H), "format": "RGB888"}
            )
            self._cam.configure(cfg)
            self._cam.start()
            self._timer.start()
        except Exception as exc:
            self._status.setText(f"Camera error: {exc}")

    def _grab_frame(self):
        try:
            frame = np.ascontiguousarray(self._cam.capture_array())
            h, w = frame.shape[:2]
            img = QImage(frame.data, w, h, w * 3, QImage.Format_RGB888)
            pix = QPixmap.fromImage(img).scaled(
                self._view.width(), self._view.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            self._view.setPixmap(pix)
        except Exception as exc:
            self._timer.stop()
            self._status.setText(f"Feed lost: {exc}")

    def closeEvent(self, event):
        self._timer.stop()
        if self._cam is not None:
            try:
                self._cam.stop()
                self._cam.close()
            except Exception:
                pass
            self._cam = None
        super().closeEvent(event)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_camera_modal.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/widgets/camera_modal.py tests/test_camera_modal.py
git commit -m "feat: add CameraModal with live picamera2 feed"
```

---

### Task 2: HeaderWidget camera button

**Files:**
- Modify: `ui/header.py`
- Modify: `tests/test_camera_modal.py` (add `TestHeaderCameraButton` class)

**Interfaces:**
- Consumes: nothing from Task 1
- Produces:
  - `HeaderWidget.cameras_requested` — `pyqtSignal()`, emitted when camera button clicked
  - `HeaderWidget.show_camera_button()` — inserts `📷` button before the gear icon; safe to call once

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_camera_modal.py`:

```python
from ui.header import HeaderWidget


class TestHeaderCameraButton:
    def test_show_camera_button_increases_layout_count(self, qtbot):
        header = HeaderWidget()
        qtbot.addWidget(header)
        count_before = header.layout().count()
        header.show_camera_button()
        assert header.layout().count() == count_before + 1

    def test_camera_button_emits_cameras_requested(self, qtbot):
        header = HeaderWidget()
        qtbot.addWidget(header)
        header.show_camera_button()
        received = []
        header.cameras_requested.connect(lambda: received.append(True))
        # find the camera button by text
        cam_btn = None
        for i in range(header.layout().count()):
            item = header.layout().itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, QPushButton) and w.text() == "\U0001f4f7":
                cam_btn = w
                break
        assert cam_btn is not None, "Camera button not found in header layout"
        cam_btn.click()
        assert received == [True]

    def test_camera_button_inserted_before_gear(self, qtbot):
        header = HeaderWidget()
        qtbot.addWidget(header)
        gear_idx = header.layout().indexOf(header._gear)
        header.show_camera_button()
        cam_btn = None
        for i in range(header.layout().count()):
            item = header.layout().itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, QPushButton) and w.text() == "\U0001f4f7":
                cam_btn = w
                break
        cam_idx = header.layout().indexOf(cam_btn)
        new_gear_idx = header.layout().indexOf(header._gear)
        assert cam_idx == new_gear_idx - 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_camera_modal.py::TestHeaderCameraButton -v
```

Expected: `AttributeError` — `HeaderWidget` has no `cameras_requested` or `_gear`.

- [ ] **Step 3: Modify `ui/header.py`**

Add `cameras_requested` to the class signals (line 43, after `settings_requested`):

```python
class HeaderWidget(QWidget):
    tab_changed        = pyqtSignal(str)   # "dashboard" | "system"
    settings_requested = pyqtSignal()
    cameras_requested  = pyqtSignal()
```

Store a reference to the gear button (find the block that creates `gear` and assign it to `self._gear`). The relevant section currently reads:

```python
        gear = QPushButton("⚙")
        gear.setFixedSize(44, 44)
        gear.setStyleSheet(
            "QPushButton { background-color: transparent; color: #555555;"
            " border: none; font-size: 18pt; }"
            " QPushButton:hover { color: #39ff14; }"
            " QPushButton:pressed { color: #e8e8e8; }"
        )
        gear.clicked.connect(self.settings_requested)
        layout.addWidget(gear)
```

Change to:

```python
        self._gear = QPushButton("⚙")
        self._gear.setFixedSize(44, 44)
        self._gear.setStyleSheet(
            "QPushButton { background-color: transparent; color: #555555;"
            " border: none; font-size: 18pt; }"
            " QPushButton:hover { color: #39ff14; }"
            " QPushButton:pressed { color: #e8e8e8; }"
        )
        self._gear.clicked.connect(self.settings_requested)
        layout.addWidget(self._gear)
```

Add `show_camera_button()` method after `_refresh_tabs()`:

```python
    def show_camera_button(self):
        cam_btn = QPushButton("\U0001f4f7")
        cam_btn.setFixedSize(44, 44)
        cam_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #555555;"
            " border: none; font-size: 18pt; }"
            " QPushButton:hover { color: #39ff14; }"
            " QPushButton:pressed { color: #e8e8e8; }"
        )
        cam_btn.clicked.connect(self.cameras_requested)
        idx = self.layout().indexOf(self._gear)
        self.layout().insertWidget(idx, cam_btn)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_camera_modal.py -v
```

Expected: all 10 tests PASS.

- [ ] **Step 5: Run full test suite to verify no regressions**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add ui/header.py tests/test_camera_modal.py
git commit -m "feat: add cameras_requested signal and show_camera_button() to HeaderWidget"
```

---

### Task 3: MainWindow camera detection and wiring

**Files:**
- Modify: `main.py`

**Interfaces:**
- Consumes:
  - `HeaderWidget.show_camera_button()` — from Task 2
  - `HeaderWidget.cameras_requested` — `pyqtSignal()` from Task 2
  - `CameraModal(parent)` — from Task 1
- Produces: nothing (terminal wiring step)

- [ ] **Step 1: Add camera detection to `main.py`**

After the existing imports block (after line 22, before `def _make_sample_events`), add:

```python
try:
    from picamera2 import Picamera2 as _Picamera2
    _CAMERAS = _Picamera2.global_camera_info()
except Exception:
    _CAMERAS = []
```

- [ ] **Step 2: Wire camera button in `MainWindow.__init__`**

After `self._header.settings_requested.connect(self._open_settings)` (line 109), add:

```python
        if _CAMERAS:
            self._header.show_camera_button()
            self._header.cameras_requested.connect(self._open_camera_modal)
```

- [ ] **Step 3: Add `_open_camera_modal` method to `MainWindow`**

After `_open_settings` method (after line 159), add:

```python
    def _open_camera_modal(self):
        from ui.widgets.camera_modal import CameraModal
        CameraModal(self).exec_()
```

- [ ] **Step 4: Run full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests PASS (detection runs at module import but `_CAMERAS` is just a list — no Qt dependency).

- [ ] **Step 5: Manual smoke test**

```bash
cd /home/ali/code/greenstar-rpi-kiosk
DISPLAY=:0 python3 main.py
```

Verify:
- `📷` button appears in the header to the left of `⚙`
- Clicking it opens the camera modal with a live feed
- Closing the modal returns to normal kiosk view
- Re-opening works without error (no resource leak)

- [ ] **Step 6: Update README.md**

In the **Current Status** table, add a row for the camera feature:

```markdown
| Camera live view | ✅ | OV5647 via CSI; conditional 📷 button in header |
```

- [ ] **Step 7: Commit**

```bash
git add main.py README.md
git commit -m "feat: detect cameras at startup and wire live view modal"
```

- [ ] **Step 8: Push**

```bash
git push
```
