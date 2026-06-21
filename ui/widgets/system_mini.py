from collections import deque

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QPen, QColor, QFont
from PyQt5.QtWidgets import QWidget, QVBoxLayout

from ui.theme import PANEL_BG, BORDER_DIM, ACCENT_GREEN, TEMP_LINE, TEXT_MID, TEXT_DIM

MINI_POINTS = 60


class _MiniGraph(QWidget):
    """Single compact metric: label + hero value + bar + mini sparkline."""

    def __init__(self, title, unit, y_min, y_max, line_color, parent=None):
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.y_min = y_min
        self.y_max = y_max
        self.line_color = line_color
        self.data = deque(maxlen=MINI_POINTS)
        self.interval_ms = 1000
        self.setMinimumHeight(80)

    def push(self, value):
        self.data.append(value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, PANEL_BG)
        painter.fillRect(0, 0, 3, h, self.line_color)
        painter.setPen(QPen(BORDER_DIM, 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        pad = 6
        inner_w = w - pad * 2

        # Title
        painter.setFont(QFont("DejaVu Sans", 8))
        painter.setPen(QPen(TEXT_MID))
        painter.drawText(pad + 4, 4, inner_w, 14, Qt.AlignLeft | Qt.AlignTop, self.title)

        # Hero value
        current = self.data[-1] if self.data else 0.0
        painter.setFont(QFont("DejaVu Sans", 18, QFont.Bold))
        painter.setPen(QPen(self.line_color))
        painter.drawText(pad, 16, inner_w, 30,
                         Qt.AlignRight | Qt.AlignVCenter,
                         f"{current:.1f}{self.unit}")

        # Bar chart
        bar_y = 50
        bar_h = 12
        bar_w = inner_w - 8
        ratio = max(0.0, min(1.0, (current - self.y_min) / (self.y_max - self.y_min)))

        bg = QColor(self.line_color); bg.setAlpha(25)
        painter.setBrush(bg)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(pad + 4, bar_y, bar_w, bar_h, 4, 4)

        if ratio > 0:
            fill = QColor(self.line_color); fill.setAlpha(200)
            painter.setBrush(fill)
            painter.drawRoundedRect(pad + 4, bar_y, int(bar_w * ratio), bar_h, 4, 4)

        # Time-window label
        if self.data:
            window_s = len(self.data) * self.interval_ms / 1000
            if window_s < 120:
                tl = f"↔ {int(window_s)}s"
            elif window_s < 7200:
                tl = f"↔ {int(window_s / 60)}m"
            else:
                tl = f"↔ {window_s / 3600:.1f}h"
            painter.setFont(QFont("DejaVu Sans", 8))
            painter.setPen(QPen(QColor("#555555")))
            painter.drawText(pad, bar_y + bar_h + 2, inner_w, 12,
                             Qt.AlignRight, tl)

        painter.end()


class SystemMiniPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self._cpu = _MiniGraph("CPU Usage",    "%",  0,  100, ACCENT_GREEN)
        self._temp = _MiniGraph("Temperature", "°C", 30,  85, TEMP_LINE)
        layout.addWidget(self._cpu)
        layout.addWidget(self._temp)
        layout.addStretch()

    def push_cpu(self, value):
        self._cpu.push(value)

    def push_temp(self, value):
        self._temp.push(value)

    def update_interval(self, ms):
        self._cpu.interval_ms = ms
        self._temp.interval_ms = ms
