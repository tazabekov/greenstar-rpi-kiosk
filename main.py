import os
import sys
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QStackedWidget

from core.bus import bus
from core.models import Transaction
from core.sampler import DataSampler
from ui.theme import BG_DARK, GLOBAL_STYLESHEET
from ui.header import HeaderWidget
from ui.screens.dashboard import DashboardScreen
from ui.screens.system import SystemScreen

SAMPLE_TRANSACTIONS = [
    Transaction(datetime.now().replace(hour=13, minute=35, second=0), "Latte",      3.90, "fiat"),
    Transaction(datetime.now().replace(hour=13, minute=28, second=0), "Espresso",   2.50, "bitcoin"),
    Transaction(datetime.now().replace(hour=13, minute=15, second=0), "Cappuccino", 4.20, "fiat"),
    Transaction(datetime.now().replace(hour=13, minute=2,  second=0), "Americano",  2.80, "fiat"),
    Transaction(datetime.now().replace(hour=12, minute=55, second=0), "Latte",      3.90, "bitcoin"),
]

SCREEN_KEYS = ["dashboard", "system"]


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        screen = QApplication.primaryScreen().size()
        self.resize(screen.width(), screen.height())
        self.move(0, 0)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header with tab navigation
        self._header = HeaderWidget()
        self._header.tab_changed.connect(self._switch_screen)
        root.addWidget(self._header)

        # Stacked screens
        self._stack = QStackedWidget()
        self._dashboard = DashboardScreen()
        self._system    = SystemScreen()
        self._stack.addWidget(self._dashboard)   # index 0 → dashboard
        self._stack.addWidget(self._system)      # index 1 → system
        root.addWidget(self._stack, stretch=1)

        # Data sampler — wired to both system screen and mini panel
        self._sampler = DataSampler()
        self._system.wire_sampler(self._sampler)
        self._sampler.cpu_sample.connect(self._dashboard.mini.push_cpu)
        self._sampler.temp_sample.connect(self._dashboard.mini.push_temp)
        self._sampler.set_interval(1000)
        self._sampler.start()

        # Pre-populate transaction list with sample data
        for tx in reversed(SAMPLE_TRANSACTIONS):
            bus.transaction_added.emit(tx)

    def set_sample_interval(self, ms):
        self._sampler.set_interval(ms)

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
    app.setStyle("Fusion")
    app.setStyleSheet(GLOBAL_STYLESHEET)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
