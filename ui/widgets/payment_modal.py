import uuid
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget,
    QLabel, QPushButton, QWidget,
)

from core.bus import bus
from core.models import Transaction

KEYPAD = [
    ["7", "8", "9"],
    ["4", "5", "6"],
    ["1", "2", "3"],
    [".", "0", "⌫"],
]

BTN_KEY = (
    "QPushButton { background-color: #1a1a1a; color: #e8e8e8;"
    " border: 1px solid #333333; border-radius: 5px;"
    " font-size: 16pt; font-weight: bold; }"
    " QPushButton:pressed { background-color: #2a2a2a; }"
)
BTN_TYPE_ACTIVE = (
    "QPushButton { background-color: #39ff14; color: #0d0d0d;"
    " border: 2px solid #39ff14; border-radius: 6px;"
    " font-size: 12pt; font-weight: bold; }"
)
BTN_TYPE_INACTIVE = (
    "QPushButton { background-color: #111111; color: #555555;"
    " border: 2px solid #333333; border-radius: 6px;"
    " font-size: 12pt; font-weight: bold; }"
    " QPushButton:hover { border-color: #39ff14; color: #39ff14; }"
)
BTN_REQUEST = (
    "QPushButton { background-color: #39ff14; color: #0d0d0d;"
    " border: none; border-radius: 6px;"
    " font-size: 13pt; font-weight: bold; }"
    " QPushButton:hover { background-color: #55ff33; }"
)
BTN_CANCEL = (
    "QPushButton { background-color: #1a1a1a; color: #888888;"
    " border: 1px solid #333333; border-radius: 6px;"
    " font-size: 12pt; }"
    " QPushButton:hover { border-color: #666666; color: #aaaaaa; }"
)


class PaymentModal(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        if parent:
            self.resize(parent.width(), parent.height())
            self.move(0, 0)

        self._digits          = ""
        self._payment_type    = "fiat"
        self._tx_id           = None
        self._dot_count       = 0
        self._dot_timer       = None   # created in _request(); guarded everywhere
        self._elapsed_s       = 0
        self._elapsed_timer   = None
        self._result_connected = False
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._card = QWidget(self)
        self._card.setStyleSheet(
            "background-color: #0d0d0d;"
            " border: 2px solid #1a5c08;"
            " border-radius: 10px;"
        )
        max_card_h = (self.height() if self.height() > 0 else 480) - 40
        self._card.setMaximumHeight(max_card_h)
        self._card.setFixedWidth(400)

        self._stack = QStackedWidget(self._card)
        card_wrap = QVBoxLayout(self._card)
        card_wrap.setContentsMargins(0, 0, 0, 0)
        card_wrap.addWidget(self._stack)

        self._stack.addWidget(self._build_input_page())       # 0
        self._stack.addWidget(self._build_processing_page())  # 1
        self._stack.addWidget(self._build_result_page())      # 2

        outer.addStretch()
        h_row = QHBoxLayout()
        h_row.addStretch()
        h_row.addWidget(self._card)
        h_row.addStretch()
        outer.addLayout(h_row)
        outer.addStretch()

    def _build_input_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(8)

        title = QLabel("New Payment")
        title.setStyleSheet(
            "color: #39ff14; font-size: 15pt; font-weight: bold; border: none;"
        )
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self._amount_label = QLabel("0.00")
        self._amount_label.setStyleSheet(
            "color: #e8e8e8; font-size: 30pt; font-weight: bold;"
            " background-color: #111111; border: 1px solid #333333;"
            " border-radius: 6px; padding: 4px 12px;"
        )
        self._amount_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._amount_label.setFixedHeight(56)
        layout.addWidget(self._amount_label)

        type_row = QHBoxLayout()
        type_row.setSpacing(8)
        self._type_btns = {}
        for key, label in [("fiat", "FIAT"), ("bitcoin", "₿  Bitcoin")]:
            btn = QPushButton(label)
            btn.setFixedHeight(44)   # meets 44px touch-target minimum
            btn.clicked.connect(lambda _, k=key: self._set_type(k))
            type_row.addWidget(btn)
            self._type_btns[key] = btn
        layout.addLayout(type_row)
        self._refresh_type_buttons()

        grid = QGridLayout()
        grid.setSpacing(6)
        for row_i, row in enumerate(KEYPAD):
            for col_i, key in enumerate(row):
                btn = QPushButton(key)
                btn.setFixedHeight(44)
                btn.setStyleSheet(BTN_KEY)
                btn.clicked.connect(lambda _, k=key: self._key_press(k))
                grid.addWidget(btn, row_i, col_i)
        layout.addLayout(grid)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(44)
        cancel.setStyleSheet(BTN_CANCEL)
        cancel.clicked.connect(self.reject)
        action_row.addWidget(cancel)

        request = QPushButton("Request Payment")
        request.setFixedHeight(44)
        request.setStyleSheet(BTN_REQUEST)
        request.clicked.connect(self._request)
        action_row.addWidget(request, stretch=2)

        layout.addLayout(action_row)
        return page

    def _build_processing_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addStretch()

        self._processing_lbl = QLabel("Processing")
        self._processing_lbl.setAlignment(Qt.AlignCenter)
        self._processing_lbl.setStyleSheet(
            "color: #39ff14; font-size: 18pt; font-weight: bold; border: none;"
        )
        layout.addWidget(self._processing_lbl)

        self._processing_sub = QLabel("Waiting for payment terminal…")
        self._processing_sub.setAlignment(Qt.AlignCenter)
        self._processing_sub.setStyleSheet("color: #909090; font-size: 11pt; border: none;")
        layout.addWidget(self._processing_sub)

        self._elapsed_lbl = QLabel("")
        self._elapsed_lbl.setAlignment(Qt.AlignCenter)
        self._elapsed_lbl.setStyleSheet("color: #444444; font-size: 9pt; border: none;")
        layout.addWidget(self._elapsed_lbl)

        layout.addStretch()

        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(44)
        cancel.setStyleSheet(BTN_CANCEL)
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)
        return page

    def _build_result_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.addStretch()

        self._result_icon = QLabel("✓")
        self._result_icon.setAlignment(Qt.AlignCenter)
        self._result_icon.setStyleSheet(
            "color: #39ff14; font-size: 40pt; border: none;"
        )
        layout.addWidget(self._result_icon)

        self._result_lbl = QLabel("")
        self._result_lbl.setAlignment(Qt.AlignCenter)
        self._result_lbl.setStyleSheet(
            "color: #e8e8e8; font-size: 14pt; font-weight: bold; border: none;"
        )
        layout.addWidget(self._result_lbl)

        layout.addStretch()
        return page

    # ── Input page logic ──────────────────────────────────────────────

    def _key_press(self, key):
        if key == "⌫":
            self._digits = self._digits[:-1]
        elif key == ".":
            if "." not in self._digits:
                self._digits += "."
        else:
            if "." in self._digits and len(self._digits.split(".")[1]) >= 2:
                return
            self._digits += key
        self._refresh_amount()

    def _refresh_amount(self):
        if not self._digits or self._digits == ".":
            self._amount_label.setText("0.00")
            return
        try:
            val = float(self._digits)
            dec = self._digits.split(".")[1] if "." in self._digits else ""
            self._amount_label.setText(f"{val:.{len(dec)}f}" if dec else self._digits)
        except ValueError:
            self._amount_label.setText("0.00")

    def _set_type(self, key):
        self._payment_type = key
        self._refresh_type_buttons()

    def _refresh_type_buttons(self):
        for key, btn in self._type_btns.items():
            btn.setStyleSheet(BTN_TYPE_ACTIVE if key == self._payment_type else BTN_TYPE_INACTIVE)

    # ── Payment flow ──────────────────────────────────────────────────

    def _request(self):
        try:
            amount = float(self._digits) if self._digits else 0.0
        except ValueError:
            amount = 0.0

        if amount <= 0:
            orig = self._amount_label.styleSheet()
            self._amount_label.setStyleSheet(orig.replace("#e8e8e8", "#ff4444"))
            # Parent the timer to the label so Qt cancels it if the widget is
            # destroyed before the 600ms fires (e.g. user taps Cancel quickly).
            t = QTimer(self._amount_label)
            t.setSingleShot(True)
            t.timeout.connect(lambda: self._amount_label.setStyleSheet(orig))
            t.start(600)
            return

        tx = Transaction(
            time=datetime.now(),
            item="Manual Entry",
            amount=amount,
            payment_type=self._payment_type,
            status="pending",
        )
        self._tx_id = tx.tx_id
        bus.transaction_added.emit(tx)

        # Connect to result — UniqueConnection prevents double-connect on rapid taps
        bus.payment_result.connect(self._on_result, Qt.UniqueConnection)
        self._result_connected = True

        # Animated dots on processing label
        self._dot_count = 0
        self._dot_timer = QTimer(self)
        self._dot_timer.timeout.connect(self._tick_dots)
        self._dot_timer.start(500)

        # Elapsed time counter
        self._elapsed_s = 0
        self._elapsed_lbl.setText("")
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)
        self._elapsed_timer.start(1000)

        self._stack.setCurrentIndex(1)
        bus.payment_requested.emit(tx.tx_id, amount, self._payment_type)

    def _tick_dots(self):
        self._dot_count = (self._dot_count + 1) % 4
        self._processing_lbl.setText("Processing" + "." * self._dot_count)

    def _tick_elapsed(self):
        self._elapsed_s += 1
        self._elapsed_lbl.setText(f"{self._elapsed_s}s")

    def _on_result(self, tx_id, success, message):
        if tx_id != self._tx_id:
            return
        self._cleanup_timers()
        if self._result_connected:
            bus.payment_result.disconnect(self._on_result)
            self._result_connected = False

        if success:
            self._result_icon.setText("✓")
            self._result_icon.setStyleSheet("color: #39ff14; font-size: 40pt; border: none;")
            self._result_lbl.setText(message)
        else:
            self._result_icon.setText("✕")
            self._result_icon.setStyleSheet("color: #ff4444; font-size: 40pt; border: none;")
            self._result_lbl.setText(message)

        self._stack.setCurrentIndex(2)
        QTimer.singleShot(2500, self.accept)

    def _cleanup_timers(self):
        if self._dot_timer and self._dot_timer.isActive():
            self._dot_timer.stop()
        if self._elapsed_timer and self._elapsed_timer.isActive():
            self._elapsed_timer.stop()

    # ── Lifecycle ─────────────────────────────────────────────────────

    def closeEvent(self, event):
        """Ensure signal is always disconnected regardless of how the dialog closes."""
        if self._result_connected:
            bus.payment_result.disconnect(self._on_result)
            self._result_connected = False
        self._cleanup_timers()
        super().closeEvent(event)

    # ── Overlay background ────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 180))
