import logging
import threading
import time

log = logging.getLogger(__name__)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
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
_CAP_W, _CAP_H = 2592, 1944  # OV5647 full sensor resolution


class CameraModal(QDialog):
    _frame_ready = pyqtSignal(object)  # numpy array, delivered on main thread
    _feed_error  = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        if parent:
            self.resize(parent.width(), parent.height())
            self.move(0, 0)
        self._cam = None
        self._running = False
        self._last_frame_time = 0.0
        self._consecutive_errors = 0
        self._frame_ready.connect(self._show_frame)
        self._feed_error.connect(self._feed_lost)
        self._build_ui()

    def _build_ui(self):
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

        # Video view — fills all available space, ignores pixmap sizeHint
        self._view = QLabel()
        self._view.setAlignment(Qt.AlignCenter)
        self._view.setStyleSheet(_VIEW_STYLE)
        self._view.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        vbox.addWidget(self._view, stretch=1)

        # Status — shows "● Live" while running, error text on failure
        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setStyleSheet(_STATUS_STYLE)
        vbox.addWidget(self._status)

        # Close button
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
        self._start_camera()

    def _start_camera(self):
        if self._cam is not None:
            return
        from core.camera_lock import camera_lock
        if not camera_lock.acquire(blocking=False):
            self._status.setText("Camera busy — try again shortly")
            return
        try:
            from picamera2 import Picamera2
            self._cam = Picamera2(0)
            cfg = self._cam.create_preview_configuration(
                main={"size": (_CAP_W, _CAP_H), "format": "RGB888"},
            )
            self._cam.configure(cfg)
            self._cam.post_callback = self._on_frame
            self._running = True
            self._cam.start()
            self._status.setText("● Live")
            log.info("camera started %dx%d", _CAP_W, _CAP_H)
        except Exception as exc:
            log.exception("camera start failed")
            camera_lock.release()
            self._status.setText(f"Camera error: {exc}")

    def _on_frame(self, request):
        """picamera2 internal thread: throttle to ~15 fps, emit pre-scaled QImage."""
        if not self._running:
            return
        now = time.monotonic()
        if now - self._last_frame_time < _FRAME_INTERVAL:
            return
        self._last_frame_time = now
        try:
            arr = request.make_array("main")
            h, w = arr.shape[:2]
            # Format_BGR888 matches picamera2 "RGB888" wire order (actually BGR).
            # Avoids a full-resolution channel-flip copy — arr.data is used directly.
            # .copy() gives Qt ownership of the pixels before arr goes out of scope.
            img = QImage(arr.data, w, h, arr.strides[0], QImage.Format_BGR888).copy()
            vw, vh = self._view.width(), self._view.height()
            if vw > 0 and vh > 0:
                img = img.scaled(vw, vh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if self._consecutive_errors > 0:
                log.info("frame ok after %d error(s)", self._consecutive_errors)
            self._consecutive_errors = 0
            self._frame_ready.emit(img)
        except Exception as exc:
            self._consecutive_errors += 1
            log.warning("frame error #%d: %s", self._consecutive_errors, exc)
            if self._consecutive_errors >= 5:
                self._feed_error.emit(str(exc))

    def _show_frame(self, img):
        """Main thread: convert pre-scaled QImage to pixmap and display."""
        if not self._running:
            return
        self._view.setPixmap(QPixmap.fromImage(img))

    def _feed_lost(self, msg: str):
        """Main thread: show error after 5 consecutive failures."""
        log.error("feed lost: %s", msg)
        self._running = False
        self._status.setText(f"Feed lost: {msg}")

    def closeEvent(self, event):
        log.info("closing camera modal")
        self._running = False
        cam, self._cam = self._cam, None
        if cam is not None:
            try:
                cam.post_callback = None  # stop callbacks before tearing down
            except Exception:
                pass
            # cam.stop()/close() can block if libcamera is mid-frame; run in a
            # daemon thread so closeEvent always returns immediately.
            threading.Thread(target=self._stop_camera, args=(cam,), daemon=True).start()
        super().closeEvent(event)

    @staticmethod
    def _stop_camera(cam):
        try:
            cam.stop()
            cam.close()
        except Exception:
            pass
        finally:
            from core.camera_lock import camera_lock
            try:
                camera_lock.release()
            except RuntimeError:
                pass  # wasn't locked (camera never fully started)
