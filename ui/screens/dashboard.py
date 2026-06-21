from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton

from ui.theme import BTN_PRIMARY
from ui.widgets.transaction_list import TransactionList
from ui.widgets.system_mini import SystemMiniPanel
from ui.widgets.payment_modal import PaymentModal


class DashboardScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left: transaction log + payment button ──────────────
        left = QWidget()
        left.setStyleSheet("background-color: #0d0d0d;")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)

        self.txn_list = TransactionList()
        lv.addWidget(self.txn_list, stretch=1)

        pay_btn = QPushButton("Test Payment")
        pay_btn.setFixedHeight(62)
        pay_btn.setStyleSheet(BTN_PRIMARY)
        pay_btn.clicked.connect(self._open_payment)
        lv.addWidget(pay_btn)

        root.addWidget(left, stretch=1)

        # ── Divider ─────────────────────────────────────────────
        divider = QWidget()
        divider.setFixedWidth(2)
        divider.setStyleSheet("background-color: #1a5c08;")
        root.addWidget(divider)

        # ── Right: system mini panel ─────────────────────────────
        self.mini = SystemMiniPanel()
        self.mini.setFixedWidth(210)
        self.mini.setStyleSheet("background-color: #0a0a0a;")
        root.addWidget(self.mini)

    def _open_payment(self):
        modal = PaymentModal(self.window())
        modal.exec_()
