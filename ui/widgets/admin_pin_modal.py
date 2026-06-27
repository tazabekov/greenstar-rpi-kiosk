import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

_TITLE_STYLE  = "color: #e8e8e8; font-size: 15pt; font-weight: bold; border: none;"
_BODY_STYLE   = "color: #888888; font-size: 11pt; border: none;"
_ERROR_STYLE  = "color: #cc3333; font-size: 10pt; border: none;"
_INPUT_STYLE  = (
    "QLineEdit { background-color: #1a1a1a; color: #e8e8e8;"
    " border: 1px solid #444444; border-radius: 6px;"
    " font-size: 18pt; padding: 8px; }"
    " QLineEdit:focus { border-color: #6366f1; }"
)
_UNLOCK_STYLE = (
    "QPushButton { background-color: #1e3a8a; color: #e8e8e8;"
    " border: none; border-radius: 6px; font-size: 13pt; font-weight: bold; }"
    " QPushButton:hover { background-color: #2563eb; }"
    " QPushButton:pressed { background-color: #3b82f6; }"
)
_CANCEL_STYLE = (
    "QPushButton { background-color: #1a1a1a; color: #888888;"
    " border: 1px solid #333333; border-radius: 6px; font-size: 12pt; }"
    " QPushButton:hover { border-color: #666666; color: #aaaaaa; }"
    " QPushButton:pressed { background-color: #2a2a2a; }"
)


class AdminPinModal(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        if parent:
            self.resize(parent.width(), parent.height())
            self.move(0, 0)
        self._correct_pin = os.environ.get("GKM_ADMIN_PIN", "")
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

        title = QLabel("Admin Access")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(_TITLE_STYLE)
        vbox.addWidget(title)

        body = QLabel("Enter PIN to continue.")
        body.setAlignment(Qt.AlignCenter)
        body.setStyleSheet(_BODY_STYLE)
        vbox.addWidget(body)

        vbox.addSpacing(4)

        self._pin_input = QLineEdit()
        self._pin_input.setEchoMode(QLineEdit.Password)
        self._pin_input.setAlignment(Qt.AlignCenter)
        self._pin_input.setMaxLength(20)
        self._pin_input.setFixedHeight(56)
        self._pin_input.setStyleSheet(_INPUT_STYLE)
        self._pin_input.returnPressed.connect(self._on_unlock)
        vbox.addWidget(self._pin_input)

        self._error_label = QLabel("")
        self._error_label.setAlignment(Qt.AlignCenter)
        self._error_label.setStyleSheet(_ERROR_STYLE)
        self._error_label.hide()
        vbox.addWidget(self._error_label)

        vbox.addSpacing(4)

        unlock_btn = QPushButton("Unlock")
        unlock_btn.setFixedHeight(52)
        unlock_btn.setStyleSheet(_UNLOCK_STYLE)
        unlock_btn.clicked.connect(self._on_unlock)
        vbox.addWidget(unlock_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(52)
        cancel_btn.setStyleSheet(_CANCEL_STYLE)
        cancel_btn.clicked.connect(self.reject)
        vbox.addWidget(cancel_btn)

        self._pin_input.setFocus()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 200))

    def _on_unlock(self):
        if self._pin_input.text() == self._correct_pin:
            self.accept()
        else:
            self._error_label.setText("Incorrect PIN.")
            self._error_label.show()
            self._pin_input.clear()
            self._pin_input.setFocus()
