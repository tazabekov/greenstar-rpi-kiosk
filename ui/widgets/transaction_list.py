from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QPen, QColor, QFont
from PyQt5.QtWidgets import QWidget

from ui.theme import ACCENT_GREEN, TEXT_MID, TEXT_DIM, TEXT_WHITE
from core.bus import bus

ROW_H    = 46
MAX_ROWS = 50

TYPE_COLOR = {"fiat": QColor("#39ff14"), "bitcoin": QColor("#f7931a")}
TYPE_LABEL = {"fiat": "FIAT",            "bitcoin": "₿"}

STATUS_DOT = {
    "completed": QColor("#39ff14"),
    "pending":   QColor("#f0a000"),
    "failed":    QColor("#ff4444"),
}


class TransactionList(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._transactions = []
        self._pressed_idx  = -1
        bus.transaction_added.connect(self._on_added)
        bus.transaction_event.connect(self._on_event)
        bus.payment_result.connect(self._on_result)
        self.setMinimumWidth(200)

    # ── Bus handlers ────────────────────────────────────────────────

    def _on_added(self, tx):
        self._transactions.insert(0, tx)
        if len(self._transactions) > MAX_ROWS:
            self._transactions.pop()  # oldest entry evicted silently
        self.update()

    def _on_event(self, tx_id, event):
        tx = self._find(tx_id)
        if tx:
            tx.events.append(event)

    def _on_result(self, tx_id, success, message):
        tx = self._find(tx_id)
        if tx:
            tx.status = "completed" if success else "failed"
            self.update()

    def _find(self, tx_id):
        for tx in self._transactions:
            if tx.tx_id == tx_id:
                return tx
        return None

    # ── Touch interaction ─────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        idx = event.y() // ROW_H
        if 0 <= idx < len(self._transactions):
            self._pressed_idx = idx
            self.update()  # show press highlight immediately

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        idx = event.y() // ROW_H
        # Only open if finger lifted on same row it pressed (avoids accidental scroll-taps)
        if idx == self._pressed_idx and 0 <= idx < len(self._transactions):
            self._open_detail(self._transactions[idx])
        self._pressed_idx = -1
        self.update()

    def _open_detail(self, tx):
        from ui.widgets.transaction_detail_modal import TransactionDetailModal
        modal = TransactionDetailModal(tx, self.window())
        modal.exec_()

    # ── Painting ─────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, QColor("#0d0d0d"))

        if not self._transactions:
            painter.setFont(QFont("DejaVu Sans", 11))
            painter.setPen(QPen(TEXT_DIM))
            painter.drawText(0, 0, w, h, Qt.AlignCenter, "No transactions yet")
            painter.end()
            return

        visible = min(len(self._transactions), h // ROW_H)

        for i in range(visible):
            tx = self._transactions[i]
            y  = i * ROW_H

            # Row background — brighter when pressed
            if i == self._pressed_idx:
                painter.fillRect(0, y, w, ROW_H, QColor("#1e2e1e"))
            elif i % 2 == 0:
                painter.fillRect(0, y, w, ROW_H, QColor("#111111"))

            # Pending left-edge accent bar (orange) to make status obvious at a glance
            if tx.status == "pending":
                painter.fillRect(0, y, 3, ROW_H, QColor("#f0a000"))

            # Separator
            painter.setPen(QPen(QColor("#1e1e1e"), 1))
            painter.drawLine(0, y + ROW_H - 1, w, y + ROW_H - 1)

            pad = 12
            cy  = y + ROW_H // 2

            # Time
            painter.setFont(QFont("DejaVu Sans", 10))
            painter.setPen(QPen(TEXT_MID))
            painter.drawText(pad, cy - 10, 52, 20,
                             Qt.AlignLeft | Qt.AlignVCenter,
                             tx.time.strftime("%H:%M"))

            # Payment type badge
            ptype  = tx.payment_type
            pcol   = TYPE_COLOR.get(ptype, ACCENT_GREEN)
            plabel = TYPE_LABEL.get(ptype, ptype.upper())
            bx = pad + 56
            bw = 36
            bg = QColor(pcol)
            bg.setAlpha(30)
            painter.setBrush(bg)
            painter.setPen(QPen(Qt.NoPen))
            painter.drawRoundedRect(bx, cy - 10, bw, 20, 4, 4)
            painter.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
            painter.setPen(QPen(pcol))
            painter.drawText(bx, cy - 10, bw, 20, Qt.AlignCenter, plabel)

            # Item name
            painter.setFont(QFont("DejaVu Sans", 12))
            painter.setPen(QPen(TEXT_WHITE))
            item_x = bx + bw + 10
            painter.drawText(item_x, cy - 10, w - item_x - 90, 20,
                             Qt.AlignLeft | Qt.AlignVCenter, tx.item)

            # Amount
            painter.setFont(QFont("DejaVu Sans", 13, QFont.Bold))
            painter.setPen(QPen(ACCENT_GREEN))
            painter.drawText(w - 85, cy - 10, 73, 20,
                             Qt.AlignRight | Qt.AlignVCenter,
                             f"${tx.amount:.2f}")

            # Status dot
            dot_col = STATUS_DOT.get(tx.status, QColor("#555555"))
            painter.setBrush(dot_col)
            painter.setPen(QPen(Qt.NoPen))
            painter.drawEllipse(w - 10, cy - 4, 8, 8)

        painter.end()
