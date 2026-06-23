# Camera Live View — Design Spec
Date: 2026-06-22

## Overview

Add a conditional "Cameras" button to the kiosk header that appears only when a physical camera is detected at startup. Clicking it opens a full-overlay modal that streams a live feed from the attached camera (OV5647 5MP via CSI on RPi 5).

## Scope

- Live video view only (no snapshot, no recording, no settings).
- Single camera (index 0). If multiple cameras are ever present, index 0 is used; no selector UI.
- Detection is one-shot at startup — not re-checked while the app is running.

## Components

### 1. Detection (`main.py` — `MainWindow.__init__`)

```python
from picamera2 import Picamera2
cameras = Picamera2.global_camera_info()
if cameras:
    self._header.show_camera_button()
    self._header.cameras_requested.connect(self._open_camera_modal)
```

`Picamera2.global_camera_info()` is a class method that queries libcamera without opening the device. Fast and safe to call unconditionally.

### 2. Header button (`ui/header.py` — `HeaderWidget`)

New signal:
```python
cameras_requested = pyqtSignal()
```

New method `show_camera_button()` inserts a `📷` button (44×44 px, same transparent style as the gear `⚙` button) into the layout immediately before the gear button. The button emits `cameras_requested` on click.

The button is NOT created at `__init__` time — only when `show_camera_button()` is called, so the header layout is unchanged on systems without a camera.

### 3. Modal (`ui/widgets/camera_modal.py` — `CameraModal`)

`QDialog` subclass following the exact same structure as `SettingsModal`:
- `Qt.FramelessWindowHint | Qt.Dialog`, modal, `WA_TranslucentBackground`
- Resized to cover the full parent window (full-screen overlay)
- Dark card (same `#0d0d0d` background, `#1a5c08` border, `border-radius: 10px`)

**Card layout (vertical):**
1. Title bar: `"Live Camera"` label (green, 14pt bold) + `✕` close button (top-right, same style as other modals)
2. `QLabel` (`self._view`) with `setScaledContents(False)` — pixmap set manually each frame, centered
3. Status label showing current resolution (e.g. `"640 × 480  |  15 fps"`) — static, set once on start
4. Close button (bottom, full-width, same `_CANCEL` style)

**Camera lifecycle:**
- `showEvent`: create `Picamera2(0)`, configure with `create_preview_configuration(main={"size": (640, 480), "format": "RGB888"})`, `start()`, then start `QTimer(interval=66ms)` → `_grab_frame()`
- `_grab_frame()`: `cam.capture_array()` → `QImage(data, w, h, w*3, QImage.Format_RGB888)` → `QPixmap.fromImage(img)` → scale to fit `_view` size keeping aspect ratio → `_view.setPixmap(pix)`
- `closeEvent` / close button: stop timer, `cam.stop()`, `cam.close()`, set `_cam = None`

**Error handling:** if `capture_array()` raises (camera disconnected mid-session), stop the timer and show an error label in place of the video. No crash.

### 4. MainWindow wiring

```python
def _open_camera_modal(self):
    CameraModal(self).exec_()
```

## Data flow

```
MainWindow.__init__
  └─ Picamera2.global_camera_info() → cameras found
       └─ header.show_camera_button()
            └─ cameras_requested signal ──→ MainWindow._open_camera_modal()
                                                 └─ CameraModal(self).exec_()
                                                      ├─ showEvent: Picamera2.start()
                                                      ├─ QTimer 66ms: capture_array → QPixmap → QLabel
                                                      └─ closeEvent: cam.stop() + cam.close()
```

## Dependencies

No new pip packages required. `picamera2` (v0.3.31) and `numpy` are already installed system-wide on the Pi.

`picamera2` should NOT be added to `requirements.txt` — it is a system package (`python3-picamera2`) installed via apt, not pip.

## Testing

- Unit tests cannot run picamera2 (no hardware in CI). The modal and button are excluded from automated tests.
- Manual test: launch app, verify "📷" button appears in header, click it, verify live feed appears, close, reopen — no crash, no resource leak.
- On a machine without a camera, verify the button does NOT appear.
