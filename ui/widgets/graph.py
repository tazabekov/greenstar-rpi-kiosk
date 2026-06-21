from collections import deque

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QFont, QLinearGradient, QPolygonF, QPainterPath
)
from PyQt5.QtWidgets import QWidget

from ui.theme import PANEL_BG, BORDER_DIM, TEXT_MID, TEXT_DIM

MAX_POINTS = 600


def _fmt_dur(seconds):
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m{s:02d}s" if s else f"{m}m"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m" if m else f"{h}h"


class GraphWidget(QWidget):
    def __init__(self, title, unit, y_min, y_max, line_color, y_labels, parent=None):
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.y_min = y_min
        self.y_max = y_max
        self.line_color = line_color
        self.y_labels = y_labels
        self.data = deque(maxlen=MAX_POINTS)
        self.interval_ms = 1000
        self.setMinimumHeight(100)

    def push(self, value):
        self.data.append(value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        left   = 58
        right  = 10
        top    = 52
        bottom = 32   # room for x-axis labels
        plot_w = w - left - right
        plot_h = h - top - bottom

        # Panel background
        painter.fillRect(0, 0, w, h, PANEL_BG)

        # Left-edge accent bar
        painter.fillRect(0, 0, 4, h, self.line_color)

        # Outer border
        painter.setPen(QPen(BORDER_DIM, 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        # Scan-line texture
        scanline = QColor(0, 0, 0, 45)
        painter.setPen(Qt.NoPen)
        for row in range(0, plot_h, 4):
            painter.fillRect(left, top + row, plot_w, 2, scanline)

        # Grid lines + y-axis labels
        label_font = QFont("DejaVu Sans", 11)
        painter.setFont(label_font)
        for val in self.y_labels:
            ry = (val - self.y_min) / (self.y_max - self.y_min)
            sy = int(top + plot_h - ry * plot_h)
            painter.setPen(QPen(BORDER_DIM, 1, Qt.DotLine))
            painter.drawLine(left, sy, left + plot_w, sy)
            painter.setPen(QPen(TEXT_MID, 1))
            painter.drawText(4, sy - 9, left - 8, 20,
                             Qt.AlignRight | Qt.AlignVCenter,
                             f"{int(val)}{self.unit}")

        # Title (small, understated)
        painter.setFont(QFont("DejaVu Sans", 9))
        painter.setPen(QPen(TEXT_MID))
        painter.drawText(left + 6, 4, plot_w // 2, 18,
                         Qt.AlignLeft | Qt.AlignTop, self.title)

        # Current value — hero
        if self.data:
            painter.setFont(QFont("DejaVu Sans", 28, QFont.Bold))
            painter.setPen(QPen(self.line_color))
            painter.drawText(left, 4, plot_w - 4, top - 8,
                             Qt.AlignRight | Qt.AlignVCenter,
                             f"{self.data[-1]:.1f}{self.unit}")

        if len(self.data) < 2:
            painter.setPen(QPen(TEXT_DIM))
            painter.setFont(QFont("DejaVu Sans", 10))
            painter.drawText(left, top, plot_w, plot_h,
                             Qt.AlignCenter, "Collecting data…")
        else:
            n = len(self.data)
            x_step  = plot_w / (n - 1)
            y_range = self.y_max - self.y_min

            points = []
            for i, val in enumerate(self.data):
                sx = left + i * x_step
                clamped = max(self.y_min, min(self.y_max, val))
                sy = top + plot_h - (clamped - self.y_min) / y_range * plot_h
                points.append(QPointF(sx, sy))

            # Gradient fill
            path = QPainterPath()
            path.moveTo(points[0].x(), top + plot_h)
            path.lineTo(points[0])
            for pt in points[1:]:
                path.lineTo(pt)
            path.lineTo(points[-1].x(), top + plot_h)
            path.closeSubpath()

            grad = QLinearGradient(0, top, 0, top + plot_h)
            fill = QColor(self.line_color); fill.setAlpha(90)
            fade = QColor(self.line_color); fade.setAlpha(0)
            grad.setColorAt(0.0, fill)
            grad.setColorAt(1.0, fade)
            painter.setBrush(grad)
            painter.setPen(Qt.NoPen)
            painter.drawPath(path)

            # Line
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(self.line_color, 2, Qt.SolidLine,
                                Qt.RoundCap, Qt.RoundJoin))
            painter.drawPolyline(QPolygonF(points))

            # X-axis time labels
            window_s = n * self.interval_ms / 1000
            tick_y   = top + plot_h
            x_left   = left
            x_mid    = left + plot_w // 2
            x_right  = left + plot_w

            painter.setPen(QPen(QColor("#444444"), 1))
            for x in (x_left, x_mid, x_right):
                painter.drawLine(int(x), tick_y, int(x), tick_y + 4)

            painter.setFont(QFont("DejaVu Sans", 8))
            painter.setPen(QPen(QColor("#555555")))
            lbl_y = tick_y + 5
            painter.drawText(x_left,       lbl_y, 80, 14,
                             Qt.AlignLeft,   f"−{_fmt_dur(window_s)}")
            painter.drawText(x_mid - 40,   lbl_y, 80, 14,
                             Qt.AlignCenter, f"−{_fmt_dur(window_s / 2)}")
            painter.drawText(x_right - 40, lbl_y, 40, 14,
                             Qt.AlignRight,  "now")

        painter.end()
