import os
import sys
from collections import deque

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
QPushButton#interval {
    background-color: #111111;
    color: #39ff14;
    border: 2px solid #1a5c08;
    border-radius: 8px;
    font-size: 15pt;
    font-weight: bold;
    padding: 6px 0px;
}
QPushButton#interval:hover {
    border-color: #39ff14;
    background-color: #0d1f08;
}
"""


class GraphWidget(QWidget):
    def __init__(self, title, unit, y_min, y_max, line_color, y_labels, parent=None):
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.y_min = y_min
        self.y_max = y_max
        self.line_color = line_color
        self.y_labels = y_labels  # list of numeric values to show as grid lines
        self.data = deque(maxlen=MAX_POINTS)
        self.setMinimumHeight(100)

    def push(self, value):
        self.data.append(value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # Margins
        left = 52
        right = 10
        top = 36
        bottom = 10
        plot_w = w - left - right
        plot_h = h - top - bottom

        # Background
        painter.fillRect(0, 0, w, h, PANEL_BG)

        # Border
        painter.setPen(QPen(BORDER_DIM, 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        # Grid lines and y-axis labels
        small_font = QFont("DejaVu Sans", 8)
        painter.setFont(small_font)
        painter.setPen(QPen(TEXT_DIM, 1, Qt.DotLine))
        for val in self.y_labels:
            ry = (val - self.y_min) / (self.y_max - self.y_min)
            sy = int(top + plot_h - ry * plot_h)
            painter.setPen(QPen(BORDER_DIM, 1, Qt.DotLine))
            painter.drawLine(left, sy, left + plot_w, sy)
            painter.setPen(QPen(TEXT_DIM, 1))
            label = f"{int(val)}{self.unit}"
            painter.drawText(0, sy - 8, left - 4, 18, Qt.AlignRight | Qt.AlignVCenter, label)

        # Title (top-left)
        title_font = QFont("DejaVu Sans", 11, QFont.Bold)
        painter.setFont(title_font)
        painter.setPen(QPen(ACCENT_GREEN))
        painter.drawText(left + 4, 4, plot_w // 2, top - 4, Qt.AlignLeft | Qt.AlignVCenter, self.title)

        # Current value (top-right)
        if self.data:
            current = self.data[-1]
            val_font = QFont("DejaVu Sans", 14, QFont.Bold)
            painter.setFont(val_font)
            painter.setPen(QPen(TEXT_WHITE))
            val_text = f"{current:.1f}{self.unit}"
            painter.drawText(left + plot_w // 2, 2, plot_w // 2, top - 2, Qt.AlignRight | Qt.AlignVCenter, val_text)

        if len(self.data) < 2:
            painter.setPen(QPen(TEXT_DIM))
            msg_font = QFont("DejaVu Sans", 10)
            painter.setFont(msg_font)
            painter.drawText(left, top, plot_w, plot_h, Qt.AlignCenter, "Collecting data…")
            return

        # Map data points to screen coords
        n = len(self.data)
        x_step = plot_w / (n - 1)
        y_range = self.y_max - self.y_min

        points = []
        for i, val in enumerate(self.data):
            sx = left + i * x_step
            clamped = max(self.y_min, min(self.y_max, val))
            sy = top + plot_h - (clamped - self.y_min) / y_range * plot_h
            points.append(QPointF(sx, sy))

        # Gradient fill under the line
        path = QPainterPath()
        path.moveTo(points[0].x(), top + plot_h)
        path.lineTo(points[0])
        for pt in points[1:]:
            path.lineTo(pt)
        path.lineTo(points[-1].x(), top + plot_h)
        path.closeSubpath()

        grad = QLinearGradient(0, top, 0, top + plot_h)
        fill_color = QColor(self.line_color)
        fill_color.setAlpha(80)
        bottom_color = QColor(self.line_color)
        bottom_color.setAlpha(0)
        grad.setColorAt(0.0, fill_color)
        grad.setColorAt(1.0, bottom_color)
        painter.setBrush(grad)
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)

        # Line
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(self.line_color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPolyline(QPolygonF(points))

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
        hl.setContentsMargins(16, 0, 16, 0)

        logo = QLabel("MyGreenStar")
        logo.setStyleSheet("color: #39ff14; font-size: 26pt; font-weight: bold; border: none;")
        hl.addWidget(logo)

        hl.addStretch()

        self.clock_label = QLabel()
        self.clock_label.setStyleSheet("color: #e8e8e8; font-size: 14pt; border: none;")
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
            "CPU Usage", "%", 0, 100, ACCENT_GREEN,
            [0, 25, 50, 75, 100]
        )
        self.temp_graph = GraphWidget(
            "CPU Temperature", "°C", 30, 85, TEMP_LINE,
            [30, 45, 60, 75, 85]
        )
        gl.addWidget(self.cpu_graph, stretch=1)
        gl.addWidget(self.temp_graph, stretch=1)

        root.addWidget(graphs, stretch=1)

        # ── Button bar ─────────────────────────────────────────
        bar = QWidget()
        bar.setFixedHeight(70)
        bar.setStyleSheet("background-color: #0a0a0a; border-top: 2px solid #1a5c08;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(12)

        self._interval_buttons = {}
        for label in INTERVALS:
            btn = QPushButton(label)
            btn.setFixedHeight(50)
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
        from datetime import datetime
        self.clock_label.setText(datetime.now().strftime("%H:%M:%S"))

    def _apply_button_styles(self, active_label):
        for label, btn in self._interval_buttons.items():
            btn.setStyleSheet(BTN_ACTIVE if label == active_label else BTN_INACTIVE)

    def _select_interval(self, label):
        if label == self._active_interval:
            return
        self._active_interval = label
        self._apply_button_styles(label)
        self.sampler.set_interval(INTERVALS[label])

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
