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

        def __init__(self, info, parent=None, fill=False):
            super().__init__(parent)
            self._info = info
            self._fill = fill
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
                registry.set_running_cam(self._info.idx, self._cam)
                self._status.setText(
                    f"{self._info.model} · {self._info.max_w}×{self._info.max_h} · ● Live"
                )
                log.info("camera %d started %dx%d", self._info.idx, self._info.max_w, self._info.max_h)
            except Exception as exc:
                log.exception("camera %d start failed", self._info.idx)
                registry.release(self._info.idx)
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
            from core.camera_registry import registry
            registry.set_running_cam(idx, None)
            try:
                cam.stop()
                cam.close()
            except Exception:
                pass
            finally:
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
                    if self._fill:
                        scaled = img.scaled(vw, vh, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                        x = (scaled.width() - vw) // 2
                        y = max(0, scaled.height() - vh)  # crop from top, show bottom
                        img = scaled.copy(x, y, vw, vh)
                    else:
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
            self.stop()
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
            panel = CameraModal._CameraFeedPanel(cameras[0], fill=True)
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
