from datetime import datetime

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget,
    QLabel, QPushButton, QScrollArea, QWidget,
)

from core.bus import bus
from core.config import MAX_PAYMENT_AMOUNT
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
    " QPushButton:disabled { background-color: #1a2a0d; color: #2a5010; }"
)
BTN_CANCEL = (
    "QPushButton { background-color: #1a1a1a; color: #888888;"
    " border: 1px solid #333333; border-radius: 6px;"
    " font-size: 12pt; padding: 0 16px; }"
    " QPushButton:hover { border-color: #666666; color: #aaaaaa; }"
    " QPushButton:pressed { background-color: #2a2a2a; }"
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

        self._digits           = ""
        self._payment_type     = "fiat"
        self._tx_id            = None
        self._elapsed_s        = 0
        self._elapsed_timer    = None
        self._result_connected = False
        self._event_connected  = False
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

        title = QLabel(
            'New Payment'
            '<span style="color:#555555; font-size:11pt; font-weight:normal;">'
            f'  (max ${MAX_PAYMENT_AMOUNT:.0f})</span>'
        )
        title.setTextFormat(Qt.RichText)
        title.setStyleSheet("color: #39ff14; font-size: 15pt; font-weight: bold; border: none;")
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

        self._request_btn = QPushButton("Request Payment")
        self._request_btn.setFixedHeight(44)
        self._request_btn.setStyleSheet(BTN_REQUEST)
        self._request_btn.setEnabled(False)   # disabled until a valid amount is entered
        self._request_btn.clicked.connect(self._request)
        action_row.addWidget(self._request_btn, stretch=2)

        layout.addLayout(action_row)
        return page

    def _build_processing_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(8)

        title = QLabel("Processing Payment")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #39ff14; font-size: 15pt; font-weight: bold; border: none;")
        layout.addWidget(title)

        # Scrollable live event log
        log_container = QWidget()
        log_container.setStyleSheet("background: transparent;")
        self._proc_log_layout = QVBoxLayout(log_container)
        self._proc_log_layout.setContentsMargins(6, 4, 6, 4)
        self._proc_log_layout.setSpacing(1)
        self._proc_log_layout.setAlignment(Qt.AlignTop)

        self._proc_scroll = QScrollArea()
        self._proc_scroll.setWidget(log_container)
        self._proc_scroll.setWidgetResizable(True)
        self._proc_scroll.setStyleSheet(
            "QScrollArea { background: #0a0a0a; border: 1px solid #1e2e1e; border-radius: 6px; }"
            "QScrollBar:vertical { width: 6px; background: #0a0a0a; }"
            "QScrollBar::handle:vertical { background: #2a2a2a; border-radius: 3px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        layout.addWidget(self._proc_scroll, stretch=1)

        self._elapsed_lbl = QLabel("")
        self._elapsed_lbl.setAlignment(Qt.AlignCenter)
        self._elapsed_lbl.setStyleSheet("color: #444444; font-size: 9pt; border: none;")
        layout.addWidget(self._elapsed_lbl)

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
            self._update_request_btn(0.0)
            return
        try:
            val = float(self._digits)
            dec = self._digits.split(".")[1] if "." in self._digits else ""
            self._amount_label.setText(f"{val:.{len(dec)}f}" if dec else self._digits)
            self._update_request_btn(val)
        except ValueError:
            self._amount_label.setText("0.00")
            self._update_request_btn(0.0)

    def _update_request_btn(self, amount):
        ok = 0 < amount <= MAX_PAYMENT_AMOUNT
        self._request_btn.setEnabled(ok)
        # Turn the amount label red when the limit is exceeded
        base = (
            "color: #e8e8e8; font-size: 30pt; font-weight: bold;"
            " background-color: #111111; border: 1px solid #333333;"
            " border-radius: 6px; padding: 4px 12px;"
        )
        if amount > MAX_PAYMENT_AMOUNT:
            self._amount_label.setStyleSheet(base.replace("color: #e8e8e8", "color: #ff4444"))
        else:
            self._amount_label.setStyleSheet(base)

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

        # Button is disabled below 0 and above MAX_PAYMENT_AMOUNT, so this
        # guard only fires if _request is somehow called programmatically.
        if amount <= 0 or amount > MAX_PAYMENT_AMOUNT:
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

        # Connect to live event stream for the log panel
        bus.transaction_event.connect(self._on_processing_event, Qt.UniqueConnection)
        self._event_connected = True

        # Clear any log entries from a previous run
        while self._proc_log_layout.count():
            child = self._proc_log_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Elapsed time counter
        self._elapsed_s = 0
        self._elapsed_lbl.setText("")
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)
        self._elapsed_timer.start(1000)

        self._stack.setCurrentIndex(1)
        bus.payment_requested.emit(tx.tx_id, amount, self._payment_type)

    def _tick_elapsed(self):
        self._elapsed_s += 1
        self._elapsed_lbl.setText(f"{self._elapsed_s}s")

    _SOURCE_COLORS = {
        "MDB":    "#39ff14",
        "SQUARE": "#4db8ff",
        "SYSTEM": "#666666",
    }

    def _on_processing_event(self, tx_id, event):
        if tx_id != self._tx_id:
            return
        arrow = "←" if event.direction == "in" else "→"
        color = self._SOURCE_COLORS.get(event.source, "#666666")
        ts = event.timestamp.strftime("%H:%M:%S")
        html = (
            f'<span style="color:#444444; font-family:monospace; font-size:9pt;">{ts}</span>'
            f'&nbsp;&nbsp;<span style="color:{color}; font-weight:bold; font-size:9pt;">'
            f'{event.source}&nbsp;{arrow}</span>'
            f'&nbsp;&nbsp;<span style="color:#cccccc; font-size:9pt;">{event.message}</span>'
        )
        lbl = QLabel(html)
        lbl.setTextFormat(Qt.RichText)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("border: none; padding: 2px 0;")
        self._proc_log_layout.addWidget(lbl)
        QTimer.singleShot(
            10, lambda: self._proc_scroll.verticalScrollBar().setValue(
                self._proc_scroll.verticalScrollBar().maximum()
            )
        )

    def _on_result(self, tx_id, success, message):
        if tx_id != self._tx_id:
            return
        self._cleanup_timers()
        if self._event_connected:
            try:
                bus.transaction_event.disconnect(self._on_processing_event)
            except RuntimeError:
                pass
            self._event_connected = False
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
        if self._elapsed_timer and self._elapsed_timer.isActive():
            self._elapsed_timer.stop()

    # ── Lifecycle ─────────────────────────────────────────────────────

    def closeEvent(self, event):
        """Ensure signals are always disconnected regardless of how the dialog closes."""
        if self._event_connected:
            try:
                bus.transaction_event.disconnect(self._on_processing_event)
            except RuntimeError:
                pass
            self._event_connected = False
        if self._result_connected:
            bus.payment_result.disconnect(self._on_result)
            self._result_connected = False
        self._cleanup_timers()
        super().closeEvent(event)

    # ── Overlay background ────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 180))
