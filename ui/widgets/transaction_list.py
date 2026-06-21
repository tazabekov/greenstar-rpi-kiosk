from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QPen, QColor, QFont
from PyQt5.QtWidgets import QWidget

from ui.theme import PANEL_BG, BORDER_DIM, ACCENT_GREEN, TEMP_LINE, TEXT_MID, TEXT_DIM, TEXT_WHITE
from core.bus import bus

ROW_H    = 46
MAX_ROWS = 50

# Colour per payment type
TYPE_COLOR = {
    "fiat":    QColor("#39ff14"),
    "bitcoin": QColor("#f7931a"),  # Bitcoin orange
}
TYPE_LABEL = {
    "fiat":    "FIAT",
    "bitcoin": "₿",
}


class TransactionList(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._transactions = []
        bus.transaction_added.connect(self.add)
        self.setMinimumWidth(200)

    def add(self, tx):
        self._transactions.insert(0, tx)
        if len(self._transactions) > MAX_ROWS:
            self._transactions.pop()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, QColor("#0d0d0d"))

        if not self._transactions:
            painter.setFont(QFont("DejaVu Sans", 11))
            painter.setPen(QPen(TEXT_DIM))
            painter.drawText(0, 0, w, h, Qt.AlignCenter, "No transactions yet")
            return

        visible = min(len(self._transactions), h // ROW_H)

        for i in range(visible):
            tx = self._transactions[i]
            y  = i * ROW_H

            # Alternating row tint
            if i % 2 == 0:
                painter.fillRect(0, y, w, ROW_H, QColor("#111111"))

            # Separator line
            painter.setPen(QPen(QColor("#1e1e1e"), 1))
            painter.drawLine(0, y + ROW_H - 1, w, y + ROW_H - 1)

            pad = 12
            cy  = y + ROW_H // 2

            # Time
            painter.setFont(QFont("DejaVu Sans", 10))
            painter.setPen(QPen(TEXT_MID))
            time_str = tx.time.strftime("%H:%M")
            painter.drawText(pad, cy - 10, 52, 20,
                             Qt.AlignLeft | Qt.AlignVCenter, time_str)

            # Payment type badge
            ptype  = tx.payment_type
            pcol   = TYPE_COLOR.get(ptype, ACCENT_GREEN)
            plabel = TYPE_LABEL.get(ptype, ptype.upper())
            badge_x = pad + 56
            badge_w = 36
            bg = QColor(pcol); bg.setAlpha(30)
            painter.setBrush(bg)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(badge_x, cy - 10, badge_w, 20, 4, 4)
            painter.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
            painter.setPen(QPen(pcol))
            painter.drawText(badge_x, cy - 10, badge_w, 20,
                             Qt.AlignCenter, plabel)

            # Item name
            painter.setFont(QFont("DejaVu Sans", 12))
            painter.setPen(QPen(TEXT_WHITE))
            item_x = badge_x + badge_w + 10
            painter.drawText(item_x, cy - 10, w - item_x - 90, 20,
                             Qt.AlignLeft | Qt.AlignVCenter, tx.item)

            # Amount
            painter.setFont(QFont("DejaVu Sans", 13, QFont.Bold))
            painter.setPen(QPen(ACCENT_GREEN))
            painter.drawText(w - 85, cy - 10, 73, 20,
                             Qt.AlignRight | Qt.AlignVCenter,
                             f"${tx.amount:.2f}")

            # Status dot
            dot_col = QColor("#39ff14") if tx.status == "completed" else QColor("#ff4444")
            painter.setBrush(dot_col)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(w - 10, cy - 4, 8, 8)

        painter.end()
