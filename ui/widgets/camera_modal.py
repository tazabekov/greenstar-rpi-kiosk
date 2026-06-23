import threading

import numpy as np
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
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

_FRAME_MS = 66              # ~15 fps
_CAP_W, _CAP_H = 800, 600   # preview resolution — full 5 MP stalls libcamera


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
        self._frame = None
        self._capturing = False
        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._grab_frame)
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

        # Status
        self._status = QLabel(f"{_CAP_W} × {_CAP_H}  |  15 fps")
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
        try:
            from picamera2 import Picamera2
            self._cam = Picamera2(0)
            cfg = self._cam.create_preview_configuration(
                main={"size": (_CAP_W, _CAP_H), "format": "RGB888"}
            )
            self._cam.configure(cfg)
            self._cam.start()
            self._timer.start()
        except Exception as exc:
            self._status.setText(f"Camera error: {exc}")

    def _grab_frame(self):
        """Timer callback (main thread): spawn a capture thread if none running."""
        if self._capturing or self._cam is None:
            return
        self._capturing = True
        threading.Thread(target=self._capture_worker, daemon=True).start()

    def _capture_worker(self):
        """Background thread: capture one frame, emit signal to main thread."""
        cam = self._cam
        try:
            if cam is None:
                return
            # picamera2 "RGB888" delivers bytes in BGR order; flip to RGB
            raw = cam.capture_array()[:, :, ::-1]
            frame = np.ascontiguousarray(raw)
            self._frame_ready.emit(frame)
        except Exception as exc:
            self._feed_error.emit(str(exc))
        finally:
            self._capturing = False

    def _show_frame(self, frame):
        """Main-thread: render a captured frame into the view label."""
        if not self._timer.isActive():
            return  # modal closed while frame was in flight
        h, w = frame.shape[:2]
        img = QImage(frame.data, w, h, w * 3, QImage.Format_RGB888)
        pix = QPixmap.fromImage(img).scaled(
            self._view.width(), self._view.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._view.setPixmap(pix)

    def _feed_lost(self, msg: str):
        """Main-thread: stop the timer and show an error."""
        self._timer.stop()
        self._status.setText(f"Feed lost: {msg}")

    def closeEvent(self, event):
        self._timer.stop()
        cam, self._cam = self._cam, None
        if cam is not None:
            # Stop/close in a thread — cam.stop() can block if capture_array()
            # is mid-call, which would freeze the main thread and lock the UI.
            threading.Thread(target=self._stop_camera, args=(cam,), daemon=True).start()
        super().closeEvent(event)

    @staticmethod
    def _stop_camera(cam):
        try:
            cam.stop()
            cam.close()
        except Exception:
            pass
