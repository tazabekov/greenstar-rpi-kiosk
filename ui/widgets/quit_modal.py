from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QWidget,
)

_TITLE_STYLE = "color: #e8e8e8; font-size: 15pt; font-weight: bold; border: none;"
_BODY_STYLE  = "color: #888888; font-size: 11pt; border: none;"
_QUIT_STYLE  = (
    "QPushButton { background-color: #7a1a1a; color: #e8e8e8;"
    " border: none; border-radius: 6px; font-size: 13pt; font-weight: bold; }"
    " QPushButton:hover { background-color: #cc3333; color: #ffffff; }"
    " QPushButton:pressed { background-color: #ff4444; }"
)
_CANCEL_STYLE = (
    "QPushButton { background-color: #1a1a1a; color: #888888;"
    " border: 1px solid #333333; border-radius: 6px; font-size: 12pt; }"
    " QPushButton:hover { border-color: #666666; color: #aaaaaa; }"
    " QPushButton:pressed { background-color: #2a2a2a; }"
)


class QuitModal(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        if parent:
            self.resize(parent.width(), parent.height())
            self.move(0, 0)
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch()

        card = QWidget(self)
        card.setFixedWidth(340)
        card.setStyleSheet(
            "background-color: #0d0d0d;"
            " border: 2px solid #333333; border-radius: 10px;"
        )

        center_row = QHBoxLayout()
        center_row.addStretch()
        center_row.addWidget(card)
        center_row.addStretch()
        outer.addLayout(center_row)
        outer.addStretch()

        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(24, 24, 24, 24)
        vbox.setSpacing(12)

        title = QLabel("Quit MyGreenStar?")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(_TITLE_STYLE)
        vbox.addWidget(title)

        body = QLabel("The kiosk will stop accepting payments.")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        body.setStyleSheet(_BODY_STYLE)
        vbox.addWidget(body)

        vbox.addSpacing(8)

        quit_btn = QPushButton("Quit")
        quit_btn.setFixedHeight(52)
        quit_btn.setStyleSheet(_QUIT_STYLE)
        quit_btn.clicked.connect(self._on_quit)
        vbox.addWidget(quit_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(52)
        cancel_btn.setStyleSheet(_CANCEL_STYLE)
        cancel_btn.clicked.connect(self.reject)
        vbox.addWidget(cancel_btn)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 200))

    def _on_quit(self):
        self.accept()
