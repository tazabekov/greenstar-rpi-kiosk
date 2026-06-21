from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QColor, QPainter, QPen, QFont, QBrush
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QScrollArea,
    QWidget, QPushButton, QLabel,
)

from core.bus import bus

# Source badge colour scheme
SOURCE_STYLE = {
    "MDB":    {"bg": QColor("#0d2d0d"), "border": QColor("#39ff14"), "text": QColor("#39ff14")},
    "SQUARE": {"bg": QColor("#0a1a3a"), "border": QColor("#4db8ff"), "text": QColor("#4db8ff")},
    "SYSTEM": {"bg": QColor("#1a1a1a"), "border": QColor("#666666"), "text": QColor("#909090")},
}

ROW_H       = 52   # px per event row
ROW_H_RAW   = 68   # px per event row that has raw data


class _EventLog(QWidget):
    """Custom-painted scrollable event log. Heights are variable per row."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._events = []
        self._row_heights = []
        self._total_h = 0
        self.setMinimumWidth(600)
        self._update_size()

    def set_events(self, events):
        self._events = list(events)
        self._recalc()
        self.update()

    def append_event(self, event):
        self._events.append(event)
        self._recalc()
        self.update()

    def _recalc(self):
        self._row_heights = [
            ROW_H_RAW if ev.raw else ROW_H for ev in self._events
        ]
        self._total_h = sum(self._row_heights) or ROW_H
        self._update_size()

    def _update_size(self):
        self.setFixedHeight(max(self._total_h, 40))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()

        if not self._events:
            painter.setFont(QFont("DejaVu Sans", 10))
            painter.setPen(QPen(QColor("#555555")))
            painter.drawText(0, 0, w, 40, Qt.AlignCenter, "No events recorded")
            return

        y = 0
        for i, (ev, rh) in enumerate(zip(self._events, self._row_heights)):
            # Row background
            bg = QColor("#111111") if i % 2 == 0 else QColor("#0d0d0d")
            painter.fillRect(0, y, w, rh, bg)

            # Separator
            painter.setPen(QPen(QColor("#1e1e1e"), 1))
            painter.drawLine(0, y + rh - 1, w, y + rh - 1)

            cy = y + rh // 2 - (8 if ev.raw else 0)

            # Timestamp
            painter.setFont(QFont("DejaVu Mono", 8))
            painter.setPen(QPen(QColor("#555555")))
            ts = ev.timestamp.strftime("%H:%M:%S.") + f"{ev.timestamp.microsecond // 1000:03d}"
            painter.drawText(10, cy - 9, 110, 18, Qt.AlignLeft | Qt.AlignVCenter, ts)

            # Source badge
            style = SOURCE_STYLE.get(ev.source, SOURCE_STYLE["SYSTEM"])
            bx, bw, bh = 128, 56, 20
            by = cy - bh // 2
            painter.setBrush(QBrush(style["bg"]))
            painter.setPen(QPen(style["border"], 1))
            painter.drawRoundedRect(bx, by, bw, bh, 4, 4)
            painter.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
            painter.setPen(QPen(style["text"]))
            painter.drawText(bx, by, bw, bh, Qt.AlignCenter, ev.source)

            # Direction arrow
            arrow = "←" if ev.direction == "in" else "→"
            arrow_col = QColor("#4db8ff") if ev.direction == "in" else QColor("#39ff14")
            painter.setFont(QFont("DejaVu Sans", 11))
            painter.setPen(QPen(arrow_col))
            painter.drawText(190, cy - 9, 20, 18, Qt.AlignCenter, arrow)

            # Message
            painter.setFont(QFont("DejaVu Sans", 10))
            painter.setPen(QPen(QColor("#e8e8e8")))
            painter.drawText(216, cy - 9, w - 226, 18,
                             Qt.AlignLeft | Qt.AlignVCenter, ev.message)

            # Raw data line (smaller, dim)
            if ev.raw:
                raw_y = cy + 12
                painter.setFont(QFont("DejaVu Mono", 8))
                painter.setPen(QPen(QColor("#4a6a4a")))
                raw_text = ev.raw if len(ev.raw) <= 90 else ev.raw[:87] + "..."
                painter.drawText(216, raw_y, w - 226, 16,
                                 Qt.AlignLeft | Qt.AlignVCenter, raw_text)

            y += rh

        painter.end()


class TransactionDetailModal(QDialog):
    def __init__(self, tx, parent=None):
        super().__init__(parent)
        self._tx = tx
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        if parent:
            self.resize(parent.width(), parent.height())
            self.move(0, 0)
        self._build_ui()
        # Listen for new events while the modal is open (e.g. active payment)
        bus.transaction_event.connect(self._on_event)
        bus.payment_result.connect(self._on_result)

    def done(self, result):
        """Disconnect bus signals before closing to prevent zombie callbacks."""
        try:
            bus.transaction_event.disconnect(self._on_event)
        except RuntimeError:
            pass
        try:
            bus.payment_result.disconnect(self._on_result)
        except RuntimeError:
            pass
        super().done(result)

    def _build_ui(self):
        tx = self._tx

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar (title + status badge only — no close button) ──
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("background-color: #0a0a0a; border-bottom: 1px solid #1a5c08;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 12, 0)

        title = QLabel(f"Transaction  #{tx.tx_id}")
        title.setStyleSheet("color: #e8e8e8; font-size: 13pt; font-weight: bold; background: none;")
        hl.addWidget(title, stretch=1)

        # Status badge
        status_colors = {
            "completed": ("#0d2d0d", "#39ff14"),
            "pending":   ("#2d2000", "#f0a000"),
            "failed":    ("#2d0000", "#ff4444"),
        }
        sbg, sfg = status_colors.get(tx.status, ("#1a1a1a", "#909090"))
        status_lbl = QLabel(tx.status.upper())
        status_lbl.setFixedSize(100, 26)
        status_lbl.setAlignment(Qt.AlignCenter)
        status_lbl.setStyleSheet(
            f"background-color: {sbg}; color: {sfg};"
            f" border: 1px solid {sfg}; border-radius: 5px; font-size: 10pt; font-weight: bold;"
        )
        self._status_lbl = status_lbl
        hl.addWidget(status_lbl)

        root.addWidget(header)

        # ── Transaction summary ──────────────────────────────────────
        summary = QWidget()
        summary.setFixedHeight(52)
        summary.setStyleSheet("background-color: #0d0d0d; border-bottom: 1px solid #222222;")
        sl = QHBoxLayout(summary)
        sl.setContentsMargins(16, 0, 16, 0)
        sl.setSpacing(20)

        time_lbl = QLabel(tx.time.strftime("%H:%M:%S"))
        time_lbl.setStyleSheet("color: #909090; font-size: 12pt;")
        sl.addWidget(time_lbl)

        item_lbl = QLabel(tx.item)
        item_lbl.setStyleSheet("color: #e8e8e8; font-size: 14pt; font-weight: bold;")
        sl.addWidget(item_lbl, stretch=1)

        type_colors = {"fiat": "#39ff14", "bitcoin": "#f7931a"}
        tc = type_colors.get(tx.payment_type, "#39ff14")
        type_lbl = QLabel("FIAT" if tx.payment_type == "fiat" else "₿ Bitcoin")
        type_lbl.setFixedSize(90, 26)
        type_lbl.setAlignment(Qt.AlignCenter)
        type_lbl.setStyleSheet(
            f"background-color: transparent; color: {tc};"
            f" border: 1px solid {tc}; border-radius: 5px; font-size: 10pt; font-weight: bold;"
        )
        sl.addWidget(type_lbl)

        amt_lbl = QLabel(f"${tx.amount:.2f}")
        amt_lbl.setStyleSheet("color: #39ff14; font-size: 16pt; font-weight: bold;")
        sl.addWidget(amt_lbl)

        root.addWidget(summary)

        # ── Event log header ─────────────────────────────────────────
        log_hdr = QWidget()
        log_hdr.setFixedHeight(30)
        log_hdr.setStyleSheet("background-color: #080808; border-bottom: 1px solid #1a1a1a;")
        lhl = QHBoxLayout(log_hdr)
        lhl.setContentsMargins(16, 0, 16, 0)

        QLabel_style = "color: #555555; font-size: 9pt;"
        lbl_hdr = QLabel("TIMESTAMP            SOURCE     DIR   MESSAGE")
        lbl_hdr.setStyleSheet(QLabel_style)
        lhl.addWidget(lbl_hdr)

        self._event_count_lbl = QLabel(f"{len(tx.events)} events")
        self._event_count_lbl.setStyleSheet("color: #555555; font-size: 9pt;")
        self._event_count_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lhl.addWidget(self._event_count_lbl)

        root.addWidget(log_hdr)

        # ── Scrollable event log ─────────────────────────────────────
        self._log_widget = _EventLog()
        self._log_widget.set_events(tx.events)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._log_widget)
        scroll.setStyleSheet(
            "QScrollArea { background-color: #0d0d0d; border: none; }"
            "QScrollBar:vertical { background: #0d0d0d; width: 8px; }"
            "QScrollBar::handle:vertical { background: #333333; border-radius: 4px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        self._scroll = scroll
        root.addWidget(scroll, stretch=1)

        # ── Full-width bottom close bar (touch-friendly, thumb-reachable) ──
        close_bar = QPushButton("✕   Close  —  tap to dismiss")
        close_bar.setFixedHeight(52)
        close_bar.setStyleSheet(
            "QPushButton { background-color: #0a0a0a; color: #555555;"
            " border: none; border-top: 1px solid #1a1a1a;"
            " font-size: 11pt; }"
            " QPushButton:pressed { background-color: #1a1a1a; color: #909090; }"
        )
        close_bar.clicked.connect(self.reject)
        root.addWidget(close_bar)

    def _on_event(self, tx_id, event):
        if tx_id != self._tx.tx_id:
            return
        self._tx.events.append(event)
        self._log_widget.append_event(event)
        self._event_count_lbl.setText(f"{len(self._tx.events)} events")
        # Auto-scroll to bottom
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_result(self, tx_id, success, message):
        if tx_id != self._tx.tx_id:
            return
        self._tx.status = "completed" if success else "failed"
        status_colors = {
            "completed": ("#0d2d0d", "#39ff14"),
            "failed":    ("#2d0000", "#ff4444"),
        }
        sbg, sfg = status_colors.get(self._tx.status, ("#1a1a1a", "#909090"))
        self._status_lbl.setText(self._tx.status.upper())
        self._status_lbl.setStyleSheet(
            f"background-color: {sbg}; color: {sfg};"
            f" border: 1px solid {sfg}; border-radius: 5px; font-size: 10pt; font-weight: bold;"
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0d0d0d"))
