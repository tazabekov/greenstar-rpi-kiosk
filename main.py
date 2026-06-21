import os
import sys
from datetime import datetime, timedelta

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QStackedWidget

from core.bus import bus
from core.models import Transaction, TransactionEvent
from core.sampler import DataSampler
from core.square import SquareMockClient   # swap for SquareClient when live
from ui.theme import BG_DARK, GLOBAL_STYLESHEET
from ui.header import HeaderWidget
from ui.screens.dashboard import DashboardScreen
from ui.screens.system import SystemScreen


def _make_sample_events(base_time, payment_type, amount, checkout_id):
    """Pre-baked event log for sample transactions shown on startup."""
    cents = int(amount * 100)
    t = base_time
    events = [
        TransactionEvent(t,                          "MDB",    "in",
                         f"VEND REQUEST  ${amount:.2f}",
                         f"0x03 0x00 {cents:04x}"),
        TransactionEvent(t + timedelta(seconds=0.3), "SQUARE", "out",
                         f"POST /v2/terminals/checkouts  ${amount:.2f} USD"
                         + (" (Bitcoin/Crypto)" if payment_type == "bitcoin" else ""),
                         f'{{"amount_money": {{"amount": {cents}, "currency": "USD"}}, ...}}'),
        TransactionEvent(t + timedelta(seconds=0.9), "SQUARE", "in",
                         f"200 OK — checkout created id={checkout_id}, status: PENDING",
                         f'{{"checkout": {{"id": "{checkout_id}", "status": "PENDING"}}}}'),
        TransactionEvent(t + timedelta(seconds=2.5), "SQUARE", "in",
                         f"GET .../{checkout_id} → IN_PROGRESS "
                         + ("(QR code displayed)" if payment_type == "bitcoin"
                            else "(payment screen shown)")),
        TransactionEvent(t + timedelta(seconds=6.1), "SQUARE", "in",
                         f"GET .../{checkout_id} → COMPLETED"),
        TransactionEvent(t + timedelta(seconds=6.3), "MDB",    "out",
                         "VEND APPROVED", "0x05 0x00"),
    ]
    return events


SAMPLE_TRANSACTIONS = [
    Transaction(
        datetime.now().replace(hour=13, minute=35, second=0),
        "Latte", 3.90, "fiat", status="completed",
        events=_make_sample_events(
            datetime.now().replace(hour=13, minute=35, second=0),
            "fiat", 3.90, "chk_sample_001")),
    Transaction(
        datetime.now().replace(hour=13, minute=28, second=0),
        "Espresso", 2.50, "bitcoin", status="completed",
        events=_make_sample_events(
            datetime.now().replace(hour=13, minute=28, second=0),
            "bitcoin", 2.50, "chk_sample_002")),
    Transaction(
        datetime.now().replace(hour=13, minute=15, second=0),
        "Cappuccino", 4.20, "fiat", status="completed",
        events=_make_sample_events(
            datetime.now().replace(hour=13, minute=15, second=0),
            "fiat", 4.20, "chk_sample_003")),
    Transaction(
        datetime.now().replace(hour=13, minute=2, second=0),
        "Americano", 2.80, "fiat", status="completed",
        events=_make_sample_events(
            datetime.now().replace(hour=13, minute=2, second=0),
            "fiat", 2.80, "chk_sample_004")),
    Transaction(
        datetime.now().replace(hour=12, minute=55, second=0),
        "Latte", 3.90, "bitcoin", status="completed",
        events=_make_sample_events(
            datetime.now().replace(hour=12, minute=55, second=0),
            "bitcoin", 3.90, "chk_sample_005")),
]

SCREEN_KEYS = ["dashboard", "system"]
_INSTANCE_KEY = "mygreenstar-kiosk"


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        screen = QApplication.primaryScreen().size()
        self.resize(screen.width(), screen.height())
        self.move(0, 0)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

        # Single-instance server — listens for "activate" from later launches
        QLocalServer.removeServer(_INSTANCE_KEY)   # clean up any stale socket
        self._ipc_server = QLocalServer(self)
        self._ipc_server.listen(_INSTANCE_KEY)
        self._ipc_server.newConnection.connect(self._on_second_instance)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._header = HeaderWidget()
        self._header.tab_changed.connect(self._switch_screen)
        root.addWidget(self._header)

        self._stack     = QStackedWidget()
        self._dashboard = DashboardScreen()
        self._system    = SystemScreen()
        self._stack.addWidget(self._dashboard)
        self._stack.addWidget(self._system)
        root.addWidget(self._stack, stretch=1)

        self._sampler = DataSampler()
        self._system.wire_sampler(self._sampler)
        self._sampler.cpu_sample.connect(self._dashboard.mini.push_cpu)
        self._sampler.temp_sample.connect(self._dashboard.mini.push_temp)
        self._sampler.set_interval(1000)
        self._sampler.start()

        # Interval changes from System screen propagate to sampler + mini panel
        self._system.interval_changed.connect(self._sampler.set_interval)
        self._system.interval_changed.connect(self._dashboard.mini.update_interval)

        # Square mock client — listens to bus.payment_requested
        self._square = SquareMockClient(self)

        # Pre-populate transaction list
        for tx in reversed(SAMPLE_TRANSACTIONS):
            bus.transaction_added.emit(tx)

    def _on_second_instance(self):
        conn = self._ipc_server.nextPendingConnection()
        conn.readyRead.connect(self._activate)

    def _activate(self):
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def _switch_screen(self, key):
        idx = SCREEN_KEYS.index(key) if key in SCREEN_KEYS else 0
        self._stack.setCurrentIndex(idx)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), BG_DARK)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            QApplication.quit()


if __name__ == "__main__":
    os.environ.setdefault("DISPLAY", ":0")
    app = QApplication(sys.argv)

    # If another instance is already running, signal it and exit immediately.
    _probe = QLocalSocket()
    _probe.connectToServer(_INSTANCE_KEY)
    if _probe.waitForConnected(500):
        _probe.write(b"activate")
        _probe.flush()
        _probe.waitForBytesWritten(500)
        _probe.disconnectFromServer()
        print("MyGreenStar kiosk is already running — bringing it to the front.")
        sys.exit(0)
    _probe.close()

    app.setStyle("Fusion")
    app.setStyleSheet(GLOBAL_STYLESHEET)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
