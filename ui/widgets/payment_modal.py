from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QWidget, QSizePolicy
)

from core.bus import bus
from core.models import Transaction
from ui.theme import BTN_PRIMARY, ACCENT_GREEN, TEXT_MID

from datetime import datetime


KEYPAD = [
    ["7", "8", "9"],
    ["4", "5", "6"],
    ["1", "2", "3"],
    [".", "0", "⌫"],
]

BTN_KEY = (
    "QPushButton { background-color: #1a1a1a; color: #e8e8e8;"
    " border: 1px solid #333333; border-radius: 6px;"
    " font-size: 18pt; font-weight: bold; }"
    " QPushButton:pressed { background-color: #2a2a2a; }"
)
BTN_TYPE_ACTIVE = (
    "QPushButton { background-color: #39ff14; color: #0d0d0d;"
    " border: 2px solid #39ff14; border-radius: 8px;"
    " font-size: 14pt; font-weight: bold; }"
)
BTN_TYPE_INACTIVE = (
    "QPushButton { background-color: #111111; color: #555555;"
    " border: 2px solid #333333; border-radius: 8px;"
    " font-size: 14pt; font-weight: bold; }"
    " QPushButton:hover { border-color: #39ff14; color: #39ff14; }"
)
BTN_CONFIRM = (
    "QPushButton { background-color: #39ff14; color: #0d0d0d;"
    " border: none; border-radius: 8px;"
    " font-size: 16pt; font-weight: bold; }"
    " QPushButton:hover { background-color: #55ff33; }"
)
BTN_CANCEL = (
    "QPushButton { background-color: #1a1a1a; color: #888888;"
    " border: 1px solid #333333; border-radius: 8px;"
    " font-size: 14pt; }"
    " QPushButton:hover { border-color: #666666; color: #aaaaaa; }"
)


class PaymentModal(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Match parent window size
        if parent:
            self.resize(parent.width(), parent.height())
            self.move(0, 0)

        self._digits = ""
        self._payment_type = "fiat"

        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Dark overlay background widget
        card = QWidget(self)
        card.setStyleSheet(
            "background-color: #0d0d0d;"
            " border: 2px solid #1a5c08;"
            " border-radius: 12px;"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(12)

        # Title
        title = QLabel("New Payment")
        title.setStyleSheet("color: #39ff14; font-size: 18pt; font-weight: bold; border: none;")
        title.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title)

        # Amount display
        self._amount_label = QLabel("0.00")
        self._amount_label.setStyleSheet(
            "color: #e8e8e8; font-size: 36pt; font-weight: bold;"
            " background-color: #111111; border: 1px solid #333333;"
            " border-radius: 8px; padding: 6px 16px;"
        )
        self._amount_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._amount_label.setFixedHeight(70)
        card_layout.addWidget(self._amount_label)

        # Payment type toggle
        type_row = QHBoxLayout()
        self._type_btns = {}
        for key, label in [("fiat", "FIAT"), ("bitcoin", "₿  Bitcoin")]:
            btn = QPushButton(label)
            btn.setFixedHeight(48)
            btn.clicked.connect(lambda _, k=key: self._set_type(k))
            type_row.addWidget(btn)
            self._type_btns[key] = btn
        card_layout.addLayout(type_row)
        self._refresh_type_buttons()

        # Keypad
        grid = QGridLayout()
        grid.setSpacing(8)
        for row_i, row in enumerate(KEYPAD):
            for col_i, key in enumerate(row):
                btn = QPushButton(key)
                btn.setFixedHeight(54)
                btn.setStyleSheet(BTN_KEY)
                btn.clicked.connect(lambda _, k=key: self._key_press(k))
                grid.addWidget(btn, row_i, col_i)
        card_layout.addLayout(grid)

        # Confirm / Cancel
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(52)
        cancel.setStyleSheet(BTN_CANCEL)
        cancel.clicked.connect(self.reject)
        action_row.addWidget(cancel)

        confirm = QPushButton("Confirm Payment")
        confirm.setFixedHeight(52)
        confirm.setStyleSheet(BTN_CONFIRM)
        confirm.clicked.connect(self._confirm)
        action_row.addWidget(confirm, stretch=2)

        card_layout.addLayout(action_row)

        # Centre the card on the overlay
        outer.addStretch()
        h_row = QHBoxLayout()
        h_row.addStretch()
        h_row.addWidget(card)
        h_row.addStretch()
        outer.addLayout(h_row)
        outer.addStretch()

        card.setFixedWidth(420)

    def paintEvent(self, event):
        painter = QPainter(self)
        overlay = QColor(0, 0, 0, 180)
        painter.fillRect(self.rect(), overlay)

    def _key_press(self, key):
        if key == "⌫":
            self._digits = self._digits[:-1]
        elif key == ".":
            if "." not in self._digits:
                self._digits += "."
        else:
            # Limit to 2 decimal places
            if "." in self._digits:
                dec = self._digits.split(".")[1]
                if len(dec) >= 2:
                    return
            self._digits += key
        self._refresh_amount()

    def _refresh_amount(self):
        if not self._digits or self._digits == ".":
            self._amount_label.setText("0.00")
        else:
            try:
                val = float(self._digits)
                if "." in self._digits:
                    dec = self._digits.split(".")[1]
                    self._amount_label.setText(f"{val:.{len(dec)}f}")
                else:
                    self._amount_label.setText(self._digits)
            except ValueError:
                self._amount_label.setText("0.00")

    def _set_type(self, key):
        self._payment_type = key
        self._refresh_type_buttons()

    def _refresh_type_buttons(self):
        for key, btn in self._type_btns.items():
            btn.setStyleSheet(BTN_TYPE_ACTIVE if key == self._payment_type else BTN_TYPE_INACTIVE)

    def _confirm(self):
        try:
            amount = float(self._digits) if self._digits else 0.0
        except ValueError:
            amount = 0.0

        if amount <= 0:
            self._amount_label.setStyleSheet(
                self._amount_label.styleSheet().replace("#e8e8e8", "#ff4444")
            )
            QTimer.singleShot(600, lambda: self._amount_label.setStyleSheet(
                self._amount_label.styleSheet().replace("#ff4444", "#e8e8e8")
            ))
            return

        # Emit payment request on the bus
        bus.payment_requested.emit(amount, self._payment_type)

        # Simulate success (real Square integration replaces this)
        tx = Transaction(
            time=datetime.now(),
            item="Manual Entry",
            amount=amount,
            payment_type=self._payment_type,
            status="completed",
        )
        bus.transaction_added.emit(tx)
        bus.payment_result.emit(True, f"${amount:.2f} accepted")

        self.accept()
