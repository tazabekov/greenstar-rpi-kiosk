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
        card.setFixedSize(700, 400)
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
        x_btn.setFixedSize(44, 44)
        x_btn.setStyleSheet(_X_STYLE)
        x_btn.clicked.connect(self.close)
        title_row.addWidget(x_btn)
        vbox.addLayout(title_row)

        # Video view
        self._view = QLabel()
        self._view.setAlignment(Qt.AlignCenter)
        self._view.setMinimumHeight(200)
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
