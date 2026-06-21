import math
import os
import sys
from collections import deque
from datetime import datetime

import psutil
from PyQt5.QtCore import Qt, QTimer, QPointF, pyqtSignal, QObject
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QFont, QLinearGradient, QPolygonF, QPainterPath
)
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

BG_DARK      = QColor("#0d0d0d")
PANEL_BG     = QColor("#111111")
BORDER_DIM   = QColor("#1a5c08")
ACCENT_GREEN = QColor("#39ff14")
TEMP_LINE    = QColor("#00c8ff")
TEXT_WHITE   = QColor("#e8e8e8")
TEXT_MID     = QColor("#909090")
TEXT_DIM     = QColor("#555555")

MAX_POINTS = 600

BTN_ACTIVE = (
    "QPushButton { background-color: #39ff14; color: #0d0d0d;"
    " border: 2px solid #39ff14; border-radius: 8px;"
    " font-size: 15pt; font-weight: bold; padding: 6px 0px; }"
)
BTN_INACTIVE = (
    "QPushButton { background-color: #111111; color: #39ff14;"
    " border: 2px solid #1a5c08; border-radius: 8px;"
    " font-size: 15pt; font-weight: bold; padding: 6px 0px; }"
    " QPushButton:hover { border-color: #39ff14; background-color: #0d1f08; }"
)

INTERVALS = {
    "1 s":  1_000,
    "10 s": 10_000,
    "1 m":  60_000,
    "1 h":  3_600_000,
}

STYLESHEET = """
QWidget {
    background-color: #0d0d0d;
    color: #e8e8e8;
    font-family: "DejaVu Sans", sans-serif;
}
"""


class StarIcon(QWidget):
    def __init__(self, size=36, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        r_outer = min(cx, cy) - 1
        r_inner = r_outer * 0.42
        pts = []
        for i in range(10):
            angle = math.radians(-90 + i * 36)
            r = r_outer if i % 2 == 0 else r_inner
            pts.append(QPointF(cx + r * math.cos(angle), cy + r * math.sin(angle)))
        path = QPainterPath()
        path.moveTo(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        path.closeSubpath()
        glow = QColor("#39ff14")
        glow.setAlpha(30)
        painter.setBrush(glow)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), r_outer + 4, r_outer + 4)
        painter.setBrush(QColor("#39ff14"))
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)


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

        # Margins — left increased to clear accent bar + give y-labels space
        left   = 58
        right  = 10
        top    = 52   # tall enough for 28pt hero number
        bottom = 20   # room for time-window label
        plot_w = w - left - right
        plot_h = h - top - bottom

        # Panel background
        painter.fillRect(0, 0, w, h, PANEL_BG)

        # Left-edge accent bar (panel identity colour)
        painter.fillRect(0, 0, 4, h, self.line_color)

        # Outer border
        painter.setPen(QPen(BORDER_DIM, 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        # Scan-line texture (CRT / oscilloscope effect)
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

        # Title — small, understated, top-left
        title_font = QFont("DejaVu Sans", 9)
        painter.setFont(title_font)
        painter.setPen(QPen(TEXT_MID))
        painter.drawText(left + 6, 4, plot_w // 2, 18,
                         Qt.AlignLeft | Qt.AlignTop, self.title)

        # Current value — HERO, 28pt bold, line colour
        if self.data:
            current = self.data[-1]
            val_font = QFont("DejaVu Sans", 28, QFont.Bold)
            painter.setFont(val_font)
            painter.setPen(QPen(self.line_color))
            painter.drawText(left, 4, plot_w - 4, top - 8,
                             Qt.AlignRight | Qt.AlignVCenter,
                             f"{current:.1f}{self.unit}")

        if len(self.data) < 2:
            painter.setPen(QPen(TEXT_DIM))
            msg_font = QFont("DejaVu Sans", 10)
            painter.setFont(msg_font)
            painter.drawText(left, top, plot_w, plot_h,
                             Qt.AlignCenter, "Collecting data…")
        else:
            n = len(self.data)
            x_step = plot_w / (n - 1)
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
            fill_color = QColor(self.line_color)
            fill_color.setAlpha(90)
            fade_color = QColor(self.line_color)
            fade_color.setAlpha(0)
            grad.setColorAt(0.0, fill_color)
            grad.setColorAt(1.0, fade_color)
            painter.setBrush(grad)
            painter.setPen(Qt.NoPen)
            painter.drawPath(path)

            # Line
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(self.line_color, 2, Qt.SolidLine,
                                Qt.RoundCap, Qt.RoundJoin))
            painter.drawPolyline(QPolygonF(points))

        # Time-window label (bottom-right, inside bottom margin)
        n = len(self.data)
        if n > 0:
            window_s = n * self.interval_ms / 1000
            if window_s < 120:
                tl = f"↔ {int(window_s)}s"
            elif window_s < 7200:
                tl = f"↔ {int(window_s / 60)}m"
            else:
                tl = f"↔ {window_s / 3600:.1f}h"
            tl_font = QFont("DejaVu Sans", 9)
            painter.setFont(tl_font)
            painter.setPen(QPen(QColor("#666666")))
            painter.drawText(left, top + plot_h + 2, plot_w, bottom - 4,
                             Qt.AlignRight | Qt.AlignVCenter, tl)

        painter.end()


class DataSampler(QObject):
    cpu_sample  = pyqtSignal(float)
    temp_sample = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        psutil.cpu_percent(interval=None)  # warm up
        self.timer = QTimer()
        self.timer.timeout.connect(self._sample)

    def set_interval(self, ms):
        was_active = self.timer.isActive()
        self.timer.stop()
        self.timer.setInterval(ms)
        if was_active:
            self.timer.start()

    def start(self):
        self.timer.start()

    def _sample(self):
        cpu = psutil.cpu_percent(interval=None)
        temps = psutil.sensors_temperatures()
        try:
            temp = temps['cpu_thermal'][0].current
        except (KeyError, IndexError, TypeError):
            try:
                temp = int(open('/sys/class/thermal/thermal_zone0/temp').read()) / 1000.0
            except OSError:
                temp = 0.0
        self.cpu_sample.emit(cpu)
        self.temp_sample.emit(temp)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        screen = QApplication.primaryScreen().size()
        self.resize(screen.width(), screen.height())
        self.move(0, 0)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self._active_interval = "1 s"
        self._build_ui()
        self._build_sampler()
        self.sampler.set_interval(INTERVALS["1 s"])
        self.sampler.start()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ─────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(64)
        header.setStyleSheet("background-color: #0a0a0a; border-bottom: 2px solid #1a5c08;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 0, 16, 0)
        hl.setSpacing(10)

        hl.addWidget(StarIcon(34))

        logo = QLabel("MyGreenStar")
        logo.setStyleSheet("color: #39ff14; font-size: 24pt; font-weight: bold; border: none;")
        hl.addWidget(logo)

        hl.addStretch()

        self.clock_label = QLabel()
        self.clock_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.clock_label.setStyleSheet("border: none;")
        hl.addWidget(self.clock_label)

        self._clock_timer = QTimer()
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        root.addWidget(header)

        # ── Graph area ─────────────────────────────────────────
        graphs = QWidget()
        graphs.setStyleSheet("background-color: #0d0d0d;")
        gl = QVBoxLayout(graphs)
        gl.setContentsMargins(10, 10, 10, 6)
        gl.setSpacing(8)

        self.cpu_graph = GraphWidget(
            "CPU Usage", "%", 0, 100, ACCENT_GREEN, [0, 25, 50, 75, 100]
        )
        self.temp_graph = GraphWidget(
            "CPU Temperature", "°C", 30, 85, TEMP_LINE, [30, 45, 60, 75, 85]
        )
        gl.addWidget(self.cpu_graph, stretch=1)
        gl.addWidget(self.temp_graph, stretch=1)

        root.addWidget(graphs, stretch=1)

        # ── Button bar ─────────────────────────────────────────
        bar = QWidget()
        bar.setFixedHeight(80)
        bar.setStyleSheet("background-color: #0a0a0a; border-top: 2px solid #1a5c08;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 10, 12, 10)
        bl.setSpacing(12)

        self._interval_buttons = {}
        for label in INTERVALS:
            btn = QPushButton(label)
            btn.setFixedHeight(60)
            btn.setMinimumWidth(90)
            btn.clicked.connect(lambda checked, l=label: self._select_interval(l))
            bl.addWidget(btn)
            self._interval_buttons[label] = btn

        self._apply_button_styles("1 s")
        root.addWidget(bar)

    def _build_sampler(self):
        self.sampler = DataSampler()
        self.sampler.cpu_sample.connect(self.cpu_graph.push)
        self.sampler.temp_sample.connect(self.temp_graph.push)

    def _update_clock(self):
        now = datetime.now()
        self.clock_label.setText(
            f"<span style='font-size:14pt; color:#e8e8e8;'>{now.strftime('%H:%M:%S')}</span>"
            f"<br><span style='font-size:9pt; color:#888888;'>{now.strftime('%a %d %b')}</span>"
        )

    def _apply_button_styles(self, active_label):
        for label, btn in self._interval_buttons.items():
            btn.setStyleSheet(BTN_ACTIVE if label == active_label else BTN_INACTIVE)

    def _select_interval(self, label):
        if label == self._active_interval:
            return
        self._active_interval = label
        self._apply_button_styles(label)
        ms = INTERVALS[label]
        self.cpu_graph.interval_ms = ms
        self.temp_graph.interval_ms = ms
        self.sampler.set_interval(ms)

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
    app.setStyleSheet(STYLESHEET)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
