# Multi-Camera Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded single-camera (OV5647) logic with dynamic discovery so any Pi camera is supported, display per-camera name and resolution in the live modal, and snapshot all attached cameras to separate Firebase Storage paths.

**Architecture:** A new `core/camera_registry.py` module probes attached cameras at startup, stores per-camera `CameraInfo` (model, resolution) and per-camera locks. `CameraModal` reads the registry and builds 1 panel (single camera), 2 side-by-side panels (two cameras), or a `QTabWidget` (3+). `Snapshotter` captures from every camera in parallel worker threads and writes each result to `kiosks/{id}/camera{n}/last-snapshot.jpg`.

**Tech Stack:** Python 3, PyQt5, picamera2, firebase-admin, pytest, pytest-qt

## Global Constraints

- Python 3.10+ (union type hints `X | Y` used throughout)
- PyQt5 — no PySide2/6. `pyqtSignal` must be a class attribute, never an instance attribute.
- picamera2 imports are always deferred to function bodies (never module-level) so tests run on non-Pi machines.
- All camera lock/unlock goes through `core.camera_registry.registry` — never open `Picamera2` without first calling `registry.acquire(idx, blocking=False)`.
- `core/camera_lock.py` is deleted in Task 2; do not re-create it or import from it.
- Commit after every task.

---

## File Map

| File | Action |
|---|---|
| `core/camera_registry.py` | CREATE — `CameraInfo` dataclass + `CameraRegistry` class + module singleton |
| `core/camera_lock.py` | DELETE |
| `core/snapshotter.py` | MODIFY — replace `_capture_jpeg(self)` with `_do_snapshot` parallel multi-cam flow |
| `ui/widgets/camera_modal.py` | REWRITE — inner `_CameraFeedPanel` class, multi-layout `CameraModal` |
| `main.py` | MODIFY — `registry.probe()` replaces `Picamera2.global_camera_info()` |
| `tests/test_camera_registry.py` | CREATE |
| `tests/test_camera_modal.py` | REWRITE |
| `tests/test_snapshotter.py` | MODIFY — update `TestSnapshotterCaptureJpeg` for new signature |
| `README.md` | MODIFY — file map, camera section |

---

## Task 1: `core/camera_registry.py`

**Files:**
- Create: `core/camera_registry.py`
- Create: `tests/test_camera_registry.py`

**Interfaces:**
- Produces:
  - `CameraInfo(idx: int, model: str, max_w: int, max_h: int)` — dataclass
  - `registry.probe() -> None`
  - `registry.cameras() -> list[CameraInfo]`
  - `registry.acquire(idx: int, blocking: bool = False) -> bool`
  - `registry.release(idx: int) -> None`

---

- [ ] **Step 1: Write the failing tests**

Create `tests/test_camera_registry.py`:

```python
import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch

from core.camera_registry import CameraInfo, CameraRegistry


def _mock_picamera2(cameras):
    """Return a mock Picamera2 class for the given list of (idx, model, w, h) tuples."""
    instances = {
        idx: MagicMock(camera_properties={"PixelArraySize": (w, h)})
        for idx, model, w, h in cameras
    }
    klass = MagicMock()
    klass.global_camera_info.return_value = [
        {"Num": idx, "Model": model} for idx, model, w, h in cameras
    ]
    klass.side_effect = lambda i: instances[i]
    return klass


class TestCameraRegistry:
    def test_probe_one_camera(self):
        reg = CameraRegistry()
        mock_cam = _mock_picamera2([(0, "ov5647", 2592, 1944)])
        with patch.dict("sys.modules", {"picamera2": MagicMock(Picamera2=mock_cam)}):
            reg.probe()
        assert reg.cameras() == [CameraInfo(idx=0, model="ov5647", max_w=2592, max_h=1944)]

    def test_probe_two_cameras(self):
        reg = CameraRegistry()
        mock_cam = _mock_picamera2([
            (0, "ov5647", 2592, 1944),
            (1, "imx219", 3280, 2464),
        ])
        with patch.dict("sys.modules", {"picamera2": MagicMock(Picamera2=mock_cam)}):
            reg.probe()
        cams = reg.cameras()
        assert len(cams) == 2
        assert cams[1] == CameraInfo(idx=1, model="imx219", max_w=3280, max_h=2464)

    def test_per_camera_locks_are_independent(self):
        reg = CameraRegistry()
        mock_cam = _mock_picamera2([
            (0, "ov5647", 2592, 1944),
            (1, "imx219", 3280, 2464),
        ])
        with patch.dict("sys.modules", {"picamera2": MagicMock(Picamera2=mock_cam)}):
            reg.probe()
        assert reg.acquire(0) is True
        assert reg.acquire(1) is True   # camera 1 unaffected by camera 0 lock
        reg.release(0)
        reg.release(1)

    def test_acquire_already_locked_returns_false(self):
        reg = CameraRegistry()
        mock_cam = _mock_picamera2([(0, "ov5647", 2592, 1944)])
        with patch.dict("sys.modules", {"picamera2": MagicMock(Picamera2=mock_cam)}):
            reg.probe()
        assert reg.acquire(0) is True
        assert reg.acquire(0) is False   # already held, non-blocking
        reg.release(0)

    def test_probe_no_picamera2(self):
        reg = CameraRegistry()
        with patch.dict("sys.modules", {"picamera2": None}):
            reg.probe()   # must not raise
        assert reg.cameras() == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/ali/code/greenstar-rpi-kiosk && python -m pytest tests/test_camera_registry.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `core.camera_registry` does not exist yet.

- [ ] **Step 3: Create `core/camera_registry.py`**

```python
import logging
import threading
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class CameraInfo:
    idx: int
    model: str
    max_w: int
    max_h: int


class CameraRegistry:
    def __init__(self):
        self._cameras: list[CameraInfo] = []
        self._locks: dict[int, threading.Lock] = {}

    def probe(self) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError:
            log.warning("CameraRegistry: picamera2 not installed — no cameras")
            return

        raw = Picamera2.global_camera_info()
        for cam_dict in raw:
            idx = cam_dict["Num"]
            model = cam_dict.get("Model", f"camera{idx}")
            try:
                cam = Picamera2(idx)
                w, h = cam.camera_properties["PixelArraySize"]
                cam.close()
            except Exception as exc:
                log.warning(
                    "CameraRegistry: failed to probe camera %d (%s) — skipping", idx, exc
                )
                continue
            self._cameras.append(CameraInfo(idx=idx, model=model, max_w=w, max_h=h))
            self._locks[idx] = threading.Lock()
            log.info("CameraRegistry: camera %d — %s %dx%d", idx, model, w, h)

    def cameras(self) -> list[CameraInfo]:
        return list(self._cameras)

    def acquire(self, idx: int, blocking: bool = False) -> bool:
        lock = self._locks.get(idx)
        if lock is None:
            return False
        return lock.acquire(blocking=blocking)

    def release(self, idx: int) -> None:
        lock = self._locks.get(idx)
        if lock is not None:
            try:
                lock.release()
            except RuntimeError:
                pass


registry = CameraRegistry()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /home/ali/code/greenstar-rpi-kiosk && python -m pytest tests/test_camera_registry.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Run the full suite to confirm no regressions**

```bash
cd /home/ali/code/greenstar-rpi-kiosk && python -m pytest tests/ -v
```

Expected: all tests pass (camera_modal tests may reference `camera_lock` — that is fixed in Task 2).

- [ ] **Step 6: Commit**

```bash
git add core/camera_registry.py tests/test_camera_registry.py
git commit -m "feat: add CameraRegistry — dynamic camera discovery and per-camera locks"
```

---

## Task 2: Delete `core/camera_lock.py` and wire `main.py`

**Files:**
- Delete: `core/camera_lock.py`
- Modify: `main.py`

**Interfaces:**
- Consumes: `registry` from `core.camera_registry` (Task 1)

---

- [ ] **Step 1: Delete `core/camera_lock.py`**

```bash
git rm core/camera_lock.py
```

- [ ] **Step 2: Update `main.py`**

Remove the module-level camera detection block:

```python
# REMOVE these lines (near the top of main.py, after imports):
try:
    from picamera2 import Picamera2 as _Picamera2
    _CAMERAS = _Picamera2.global_camera_info()
except Exception:
    _CAMERAS = []
```

Add to the import section at the top of `main.py` (after the other `from core.*` imports):

```python
from core.camera_registry import registry
```

In `MainWindow.__init__`, change the camera button block from:

```python
if _CAMERAS:
    self._header.show_camera_button()
    self._header.cameras_requested.connect(self._open_camera_modal)
```

to:

```python
if registry.cameras():
    self._header.show_camera_button()
    self._header.cameras_requested.connect(self._open_camera_modal)
```

In the `if __name__ == "__main__":` block, add `registry.probe()` after the single-instance check and before `app.setStyle(...)`:

```python
    _probe.close()

    registry.probe()   # <-- add this line

    app.setStyle("Fusion")
```

- [ ] **Step 3: Run the full test suite**

```bash
cd /home/ali/code/greenstar-rpi-kiosk && python -m pytest tests/ -v
```

Expected: all tests pass. (The `camera_modal` test still imports `camera_lock` — if it fails with ImportError, that test will be fixed in Task 4. The snapshotter tests that import `camera_lock` will also fail and are fixed in Task 3.)

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "feat: wire CameraRegistry into main.py, remove camera_lock.py"
```

---

## Task 3: Update `core/snapshotter.py`

**Files:**
- Modify: `core/snapshotter.py` (full replacement of `_do_snapshot` and `_capture_jpeg`)
- Modify: `tests/test_snapshotter.py` (update `TestSnapshotterCaptureJpeg`)

**Interfaces:**
- Consumes: `registry.cameras() -> list[CameraInfo]`, `registry.acquire()`, `registry.release()` (Task 1)
- `_capture_jpeg(self, info: CameraInfo) -> str | None` — new signature (takes `CameraInfo`, returns temp path)
- `_capture_and_upload(self, info: CameraInfo) -> str | None` — new private method; returns Storage path on success

---

- [ ] **Step 1: Replace `_do_snapshot` and `_capture_jpeg` in `core/snapshotter.py`**

Remove the existing `_do_snapshot` and `_capture_jpeg` methods and add these three in their place:

```python
def _do_snapshot(self):
    from core.camera_registry import registry
    cameras = registry.cameras()

    if not cameras:
        with self._lock:
            self._thread_running = False
        QTimer.singleShot(0, self._schedule)
        return

    results: dict[int, str | None] = {}
    results_lock = threading.Lock()

    def _capture_one(info):
        path = self._capture_and_upload(info)
        with results_lock:
            results[info.idx] = path

    threads = [
        threading.Thread(target=_capture_one, args=(info,), daemon=True)
        for info in cameras
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    captured = {idx: path for idx, path in results.items() if path is not None}
    if not captured:
        with self._lock:
            self._thread_running = False
        QTimer.singleShot(0, self._schedule)
        return

    try:
        updates: dict = {"last_snapshot_at": fb_firestore.SERVER_TIMESTAMP}
        for idx, storage_path in sorted(captured.items()):
            if idx == 0:
                updates["last_snapshot_path"] = storage_path
            else:
                updates[f"last_snapshot_path_camera{idx}"] = storage_path
        self._kiosk_ref.update(updates)
    except Exception:
        log.exception("Snapshotter: Firestore update failed — will retry next interval")
    finally:
        with self._lock:
            self._thread_running = False
        QTimer.singleShot(0, self._schedule)

def _capture_and_upload(self, info) -> str | None:
    """Capture JPEG from one camera and upload to Storage. Returns Storage path or None."""
    tmp_path = self._capture_jpeg(info)
    if tmp_path is None:
        return None
    storage_path = f"kiosks/{self._kiosk_id}/camera{info.idx}/last-snapshot.jpg"
    try:
        bucket = fb_storage.bucket(self._bucket_name)
        blob = bucket.blob(storage_path)
        blob.upload_from_filename(tmp_path, content_type="image/jpeg")
        log.info("Snapshotter: uploaded %s", storage_path)
        return storage_path
    except Exception:
        log.exception("Snapshotter: upload of camera%d failed", info.idx)
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

def _capture_jpeg(self, info) -> str | None:
    """Capture one still frame from info.idx and save to a temp JPEG. Returns path or None."""
    from core.camera_registry import registry
    if not registry.acquire(info.idx, blocking=False):
        log.info("Snapshotter: camera %d in use (CameraModal open) — skipping", info.idx)
        return None
    fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    try:
        from picamera2 import Picamera2
        cam = Picamera2(info.idx)
        cfg = cam.create_preview_configuration(
            main={"size": (info.max_w, info.max_h), "format": "RGB888"}
        )
        cam.configure(cfg)
        cam.start()
        time.sleep(2)
        cam.capture_file(tmp_path)
        cam.stop()
        cam.close()
        return tmp_path
    except Exception as exc:
        log.warning(
            "Snapshotter: camera %d capture failed (%s) — skipping", info.idx, exc
        )
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return None
    finally:
        registry.release(info.idx)
```

- [ ] **Step 2: Update `TestSnapshotterCaptureJpeg` in `tests/test_snapshotter.py`**

Replace the entire `TestSnapshotterCaptureJpeg` class with:

```python
class TestSnapshotterCaptureJpeg:
    def _make_info(self, idx=0):
        from core.camera_registry import CameraInfo
        return CameraInfo(idx=idx, model="ov5647", max_w=2592, max_h=1944)

    def test_capture_returns_none_when_picamera2_unavailable(self, qtbot, monkeypatch):
        """_capture_jpeg returns None when picamera2 raises on construction."""
        broken = types.ModuleType("picamera2")

        class _BrokenCam:
            def __init__(self, *a, **kw):
                raise RuntimeError("no camera hardware")

        broken.Picamera2 = _BrokenCam
        monkeypatch.setitem(sys.modules, "picamera2", broken)

        import core.camera_registry as _reg_mod
        mock_reg = mock.MagicMock()
        mock_reg.acquire.return_value = True
        monkeypatch.setattr(_reg_mod, "registry", mock_reg)

        s = Snapshotter()
        result = s._capture_jpeg(self._make_info())
        assert result is None

    def test_capture_cleans_up_temp_file_on_error(self, qtbot, monkeypatch, tmp_path):
        """Temp file is deleted even when capture raises."""
        created = []

        def _mkstemp(suffix=""):
            path = str(tmp_path / "snap.jpg")
            open(path, "w").close()
            created.append(path)
            import os as _os
            fd = _os.open(path, _os.O_RDWR)
            return fd, path

        monkeypatch.setattr("tempfile.mkstemp", _mkstemp)

        broken = types.ModuleType("picamera2")

        class _BrokenCam:
            def __init__(self, *a, **kw):
                raise RuntimeError("no hardware")

        broken.Picamera2 = _BrokenCam
        monkeypatch.setitem(sys.modules, "picamera2", broken)

        import core.camera_registry as _reg_mod
        mock_reg = mock.MagicMock()
        mock_reg.acquire.return_value = True
        monkeypatch.setattr(_reg_mod, "registry", mock_reg)

        s = Snapshotter()
        result = s._capture_jpeg(self._make_info())
        assert result is None
        for p in created:
            assert not os.path.exists(p), "temp file was not cleaned up"

    def test_capture_skips_when_camera_locked(self, qtbot, monkeypatch):
        """_capture_jpeg returns None immediately when registry.acquire returns False."""
        import core.camera_registry as _reg_mod
        mock_reg = mock.MagicMock()
        mock_reg.acquire.return_value = False
        monkeypatch.setattr(_reg_mod, "registry", mock_reg)

        s = Snapshotter()
        result = s._capture_jpeg(self._make_info())
        assert result is None
```

- [ ] **Step 3: Run the test suite**

```bash
cd /home/ali/code/greenstar-rpi-kiosk && python -m pytest tests/test_snapshotter.py -v
```

Expected: all snapshotter tests PASS.

- [ ] **Step 4: Run the full suite**

```bash
cd /home/ali/code/greenstar-rpi-kiosk && python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add core/snapshotter.py tests/test_snapshotter.py
git commit -m "feat: snapshotter captures all cameras in parallel, index-based Storage paths"
```

---

## Task 4: Rewrite `ui/widgets/camera_modal.py`

**Files:**
- Rewrite: `ui/widgets/camera_modal.py`
- Rewrite: `tests/test_camera_modal.py`

**Interfaces:**
- Consumes: `registry.cameras() -> list[CameraInfo]`, `registry.acquire()`, `registry.release()` (Task 1)

---

- [ ] **Step 1: Write the new tests**

Replace all content in `tests/test_camera_modal.py` with:

```python
import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock
from PyQt5.QtWidgets import QTabWidget

from core.camera_registry import CameraInfo
from ui.widgets.camera_modal import CameraModal


def _info(idx=0, model="ov5647", max_w=2592, max_h=1944):
    return CameraInfo(idx=idx, model=model, max_w=max_w, max_h=max_h)


class TestCameraModalLayout:
    def test_no_cameras_no_panels(self, qtbot):
        with patch("core.camera_registry.registry") as reg:
            reg.cameras.return_value = []
            modal = CameraModal()
            qtbot.addWidget(modal)
        assert modal._panels == []

    def test_single_camera_one_panel(self, qtbot):
        with patch("core.camera_registry.registry") as reg:
            reg.cameras.return_value = [_info(0)]
            modal = CameraModal()
            qtbot.addWidget(modal)
        assert len(modal._panels) == 1

    def test_two_cameras_two_panels_no_tabs(self, qtbot):
        with patch("core.camera_registry.registry") as reg:
            reg.cameras.return_value = [_info(0), _info(1, "imx219", 3280, 2464)]
            modal = CameraModal()
            qtbot.addWidget(modal)
        assert len(modal._panels) == 2
        assert modal.findChild(QTabWidget) is None

    def test_three_cameras_uses_tab_widget(self, qtbot):
        with patch("core.camera_registry.registry") as reg:
            reg.cameras.return_value = [
                _info(0), _info(1, "imx219", 3280, 2464), _info(2, "imx477", 4056, 3040)
            ]
            modal = CameraModal()
            qtbot.addWidget(modal)
        assert len(modal._panels) == 3
        tabs = modal.findChild(QTabWidget)
        assert tabs is not None
        assert tabs.count() == 3


class TestCameraFeedPanel:
    def test_status_initially_empty(self, qtbot):
        panel = CameraModal._CameraFeedPanel(_info())
        qtbot.addWidget(panel)
        assert panel._status.text() == ""

    def test_running_false_initially(self, qtbot):
        panel = CameraModal._CameraFeedPanel(_info())
        qtbot.addWidget(panel)
        assert panel._running is False

    def test_cam_none_initially(self, qtbot):
        panel = CameraModal._CameraFeedPanel(_info())
        qtbot.addWidget(panel)
        assert panel._cam is None

    def test_stop_sets_running_false(self, qtbot):
        panel = CameraModal._CameraFeedPanel(_info())
        qtbot.addWidget(panel)
        panel._running = True
        panel._cam = MagicMock()
        with patch("core.camera_registry.registry"):
            panel.stop()
        assert panel._running is False
        assert panel._cam is None

    def test_stop_safe_when_cam_none(self, qtbot):
        panel = CameraModal._CameraFeedPanel(_info())
        qtbot.addWidget(panel)
        panel.stop()   # must not raise


class TestHeaderQuitButton:
    def test_quit_button_present(self, qtbot):
        from ui.header import HeaderWidget
        header = HeaderWidget()
        qtbot.addWidget(header)
        assert header._quit_btn is not None

    def test_quit_button_emits_signal(self, qtbot):
        from ui.header import HeaderWidget
        header = HeaderWidget()
        qtbot.addWidget(header)
        received = []
        header.quit_requested.connect(lambda: received.append(True))
        header._quit_btn.clicked.emit()
        assert received == [True]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/ali/code/greenstar-rpi-kiosk && python -m pytest tests/test_camera_modal.py -v
```

Expected: most tests fail — `CameraModal._CameraFeedPanel` does not exist yet.

- [ ] **Step 3: Rewrite `ui/widgets/camera_modal.py`**

Replace the entire file with:

```python
import logging
import threading
import time

log = logging.getLogger(__name__)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QPushButton, QSizePolicy, QWidget,
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

_FRAME_INTERVAL = 1.0 / 15  # seconds between UI updates (~15 fps)


class CameraModal(QDialog):

    class _CameraFeedPanel(QWidget):
        _frame_ready = pyqtSignal(object)
        _feed_error  = pyqtSignal(str)

        def __init__(self, info, parent=None):
            super().__init__(parent)
            self._info = info
            self._cam = None
            self._running = False
            self._last_frame_time = 0.0
            self._consecutive_errors = 0
            self._frame_ready.connect(self._show_frame)
            self._feed_error.connect(self._on_feed_lost)
            self._build_ui()

        def _build_ui(self):
            vbox = QVBoxLayout(self)
            vbox.setContentsMargins(0, 0, 0, 0)
            vbox.setSpacing(4)

            self._view = QLabel()
            self._view.setAlignment(Qt.AlignCenter)
            self._view.setStyleSheet(_VIEW_STYLE)
            self._view.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            vbox.addWidget(self._view, stretch=1)

            self._status = QLabel("")
            self._status.setAlignment(Qt.AlignCenter)
            self._status.setStyleSheet(_STATUS_STYLE)
            vbox.addWidget(self._status)

        def start(self):
            if self._cam is not None:
                return
            from core.camera_registry import registry
            if not registry.acquire(self._info.idx, blocking=False):
                self._status.setText("Camera busy — try again shortly")
                return
            try:
                from picamera2 import Picamera2
                self._cam = Picamera2(self._info.idx)
                cfg = self._cam.create_preview_configuration(
                    main={"size": (self._info.max_w, self._info.max_h), "format": "RGB888"},
                )
                self._cam.configure(cfg)
                self._cam.post_callback = self._on_frame
                self._running = True
                self._cam.start()
                self._status.setText(
                    f"{self._info.model} · {self._info.max_w}×{self._info.max_h} · ● Live"
                )
                log.info("camera %d started %dx%d", self._info.idx, self._info.max_w, self._info.max_h)
            except Exception as exc:
                log.exception("camera %d start failed", self._info.idx)
                from core.camera_registry import registry as _reg
                _reg.release(self._info.idx)
                self._status.setText(f"Camera error: {exc}")

        def stop(self):
            self._running = False
            cam, self._cam = self._cam, None
            if cam is not None:
                try:
                    cam.post_callback = None
                except Exception:
                    pass
                threading.Thread(
                    target=CameraModal._CameraFeedPanel._stop_cam,
                    args=(cam, self._info.idx),
                    daemon=True,
                ).start()

        @staticmethod
        def _stop_cam(cam, idx):
            try:
                cam.stop()
                cam.close()
            except Exception:
                pass
            finally:
                from core.camera_registry import registry
                try:
                    registry.release(idx)
                except Exception:
                    pass

        def _on_frame(self, request):
            if not self._running:
                return
            now = time.monotonic()
            if now - self._last_frame_time < _FRAME_INTERVAL:
                return
            self._last_frame_time = now
            try:
                arr = request.make_array("main")
                h, w = arr.shape[:2]
                img = QImage(arr.data, w, h, arr.strides[0], QImage.Format_BGR888).copy()
                vw, vh = self._view.width(), self._view.height()
                if vw > 0 and vh > 0:
                    img = img.scaled(vw, vh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                if self._consecutive_errors > 0:
                    log.info("camera %d ok after %d error(s)", self._info.idx, self._consecutive_errors)
                self._consecutive_errors = 0
                self._frame_ready.emit(img)
            except Exception as exc:
                self._consecutive_errors += 1
                log.warning("camera %d frame error #%d: %s", self._info.idx, self._consecutive_errors, exc)
                if self._consecutive_errors >= 5:
                    self._feed_error.emit(str(exc))

        def _show_frame(self, img):
            if not self._running:
                return
            self._view.setPixmap(QPixmap.fromImage(img))

        def _on_feed_lost(self, msg: str):
            log.error("camera %d feed lost: %s", self._info.idx, msg)
            self._running = False
            self._status.setText(f"Feed lost: {msg}")

    # ------------------------------------------------------------------
    # CameraModal
    # ------------------------------------------------------------------

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        if parent:
            self.resize(parent.width(), parent.height())
            self.move(0, 0)
        self._panels: list[CameraModal._CameraFeedPanel] = []
        self._build_ui()

    def _build_ui(self):
        from core.camera_registry import registry
        cameras = registry.cameras()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        card = QWidget(self)
        card.setStyleSheet(
            "background-color: #0d0d0d;"
            " border: 2px solid #1a5c08; border-radius: 10px;"
        )
        outer.addWidget(card)

        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(16, 12, 16, 16)
        vbox.setSpacing(8)

        # Title row
        title_row = QHBoxLayout()
        title = QLabel("Live Camera")
        title.setStyleSheet(_TITLE_STYLE)
        title_row.addWidget(title)
        title_row.addStretch()
        x_btn = QPushButton("✕")
        x_btn.setFixedSize(44, 44)
        x_btn.setStyleSheet(_X_STYLE)
        x_btn.clicked.connect(self.close)
        title_row.addWidget(x_btn)
        vbox.addLayout(title_row)

        if not cameras:
            no_cam = QLabel("No camera detected")
            no_cam.setAlignment(Qt.AlignCenter)
            no_cam.setStyleSheet("color: #555555; font-size: 11pt; border: none;")
            vbox.addWidget(no_cam, stretch=1)
        elif len(cameras) == 1:
            panel = CameraModal._CameraFeedPanel(cameras[0])
            vbox.addWidget(panel, stretch=1)
            self._panels.append(panel)
        elif len(cameras) == 2:
            container = QWidget()
            container.setStyleSheet("border: none;")
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            for info in cameras:
                panel = CameraModal._CameraFeedPanel(info)
                row.addWidget(panel, stretch=1)
                self._panels.append(panel)
            vbox.addWidget(container, stretch=1)
        else:
            tabs = QTabWidget()
            tabs.setStyleSheet("QTabWidget::pane { border: none; }")
            for info in cameras:
                panel = CameraModal._CameraFeedPanel(info)
                tabs.addTab(panel, info.model)
                self._panels.append(panel)
            vbox.addWidget(tabs, stretch=1)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(44)
        close_btn.setStyleSheet(_CLOSE_STYLE)
        close_btn.clicked.connect(self.close)
        vbox.addWidget(close_btn)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 180))

    def showEvent(self, event):
        super().showEvent(event)
        for panel in self._panels:
            panel.start()

    def closeEvent(self, event):
        for panel in self._panels:
            panel.stop()
        super().closeEvent(event)
```

- [ ] **Step 4: Run camera modal tests**

```bash
cd /home/ali/code/greenstar-rpi-kiosk && python -m pytest tests/test_camera_modal.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Run the full suite**

```bash
cd /home/ali/code/greenstar-rpi-kiosk && python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add ui/widgets/camera_modal.py tests/test_camera_modal.py
git commit -m "feat: multi-camera modal — side-by-side for 2, tabs for 3+, dynamic resolution label"
```

---

## Task 5: Update `README.md` and memory

**Files:**
- Modify: `README.md`
- Modify: `/home/ali/.claude/projects/-home-ali-code-greenstar-rpi-kiosk/memory/project_camera_lock.md`

---

- [ ] **Step 1: Update the file map in `README.md`**

In the `## File map` section, replace:

```
core/camera_lock.py  Shared lock — any code opening Picamera2(0) must acquire this first
```

with:

```
core/camera_registry.py  CameraRegistry — discovers cameras, max resolution, per-camera locks
```

- [ ] **Step 2: Update the camera snapshot section in `README.md`**

Find the section describing the camera snapshot / Firebase Storage feature and update it to reflect:
- Multiple cameras are discovered at startup via `CameraRegistry.probe()`
- Each camera's snapshot is uploaded to `kiosks/{kiosk_id}/camera{n}/last-snapshot.jpg`
- Firestore fields: `last_snapshot_path` (camera 0, backward-compat), `last_snapshot_path_camera1`, etc.
- `CameraModal` shows model name and resolution per feed

- [ ] **Step 3: Update the memory file**

Open `/home/ali/.claude/projects/-home-ali-code-greenstar-rpi-kiosk/memory/project_camera_lock.md` and update it to reference the registry instead of camera_lock:

```markdown
---
name: project-camera-registry
description: Any code opening Picamera2 must acquire the per-camera lock from core/camera_registry.py first
metadata:
  type: project
---

Any code that opens a `Picamera2(idx)` instance must first call `registry.acquire(idx, blocking=False)` from `core.camera_registry`. Without this, concurrent access between `Snapshotter` and `CameraModal` corrupts picamera2's global listen thread, causing `AttributeError: 'Picamera2' object has no attribute 'allocator'`.

`core/camera_lock.py` was deleted in the multi-camera refactor (2026-06-23). All lock management is now through `core.camera_registry.registry`.

**Why:** Prior incident — Snapshotter creating `Picamera2(0)` while `CameraModal` held the camera crashed the picamera2 global listen thread for all instances.

**How to apply:** Any new code that opens a camera must call `registry.acquire(idx)` first and `registry.release(idx)` in a `finally` block.
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git add /home/ali/.claude/projects/-home-ali-code-greenstar-rpi-kiosk/memory/project_camera_lock.md
git commit -m "docs: update README and memory for multi-camera registry"
```

- [ ] **Step 5: Push**

```bash
git push
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by |
|---|---|
| Discover all attached cameras dynamically | Task 1 — `registry.probe()` |
| Query each camera's max resolution | Task 1 — `camera_properties['PixelArraySize']` |
| Show camera name + resolution in modal status | Task 4 — `"{model} · {w}×{h} · ● Live"` |
| 1 camera → single panel | Task 4 — `elif len(cameras) == 1` branch |
| 2 cameras → side-by-side | Task 4 — `elif len(cameras) == 2` branch |
| 3+ cameras → QTabWidget | Task 4 — `else` branch with `QTabWidget` |
| Snapshot all cameras on each tick | Task 3 — parallel `_capture_one` threads |
| Storage path `camera{n}/last-snapshot.jpg` | Task 3 — `_capture_and_upload` |
| Backward-compat `last_snapshot_path` Firestore field | Task 3 — `if idx == 0` branch |
| `camera_lock.py` deleted | Task 2 — `git rm` |
| `main.py` wired to registry | Task 2 |
| Tests for registry | Task 1 |
| Tests for modal layout | Task 4 |
| Tests for snapshotter capture | Task 3 |

**Placeholder scan:** None found.

**Type consistency:**
- `CameraInfo` defined in Task 1; consumed identically in Tasks 3 and 4 (`info.idx`, `info.model`, `info.max_w`, `info.max_h`)
- `registry.acquire(idx, blocking=False)` and `registry.release(idx)` signatures match across all tasks
- `_capture_jpeg(self, info: CameraInfo)` defined and called with `CameraInfo` throughout Task 3
