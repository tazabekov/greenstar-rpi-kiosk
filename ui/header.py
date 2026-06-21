import math
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, QPointF, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPainterPath, QPen
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

from ui.theme import BTN_ACTIVE, BTN_INACTIVE


class StarIcon(QWidget):
    def __init__(self, size=34, parent=None):
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


class HeaderWidget(QWidget):
    tab_changed = pyqtSignal(str)   # "dashboard" | "system"

    TABS = [("dashboard", "Dashboard"), ("system", "System")]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setStyleSheet("background-color: #0a0a0a; border-bottom: 2px solid #1a5c08;")
        self._active_tab = "dashboard"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 16, 0)
        layout.setSpacing(10)

        layout.addWidget(StarIcon(34))

        logo = QLabel("MyGreenStar")
        logo.setStyleSheet("color: #39ff14; font-size: 22pt; font-weight: bold; border: none;")
        layout.addWidget(logo)

        layout.addStretch()

        self._tab_buttons = {}
        for key, label in self.TABS:
            btn = QPushButton(label)
            btn.setFixedHeight(44)
            btn.setMinimumWidth(110)
            btn.clicked.connect(lambda _, k=key: self._on_tab(k))
            layout.addWidget(btn)
            self._tab_buttons[key] = btn

        layout.addSpacing(12)

        self._clock = QLabel()
        self._clock.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._clock.setStyleSheet("border: none;")
        layout.addWidget(self._clock)

        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(1000)
        self._tick()

        self._refresh_tabs()

    def _tick(self):
        now = datetime.now()
        self._clock.setText(
            f"<span style='font-size:13pt;color:#e8e8e8;'>{now.strftime('%H:%M:%S')}</span>"
            f"<br><span style='font-size:8pt;color:#888888;'>{now.strftime('%a %d %b')}</span>"
        )

    def _on_tab(self, key):
        if key == self._active_tab:
            return
        self._active_tab = key
        self._refresh_tabs()
        self.tab_changed.emit(key)

    def _refresh_tabs(self):
        for key, btn in self._tab_buttons.items():
            btn.setStyleSheet(BTN_ACTIVE if key == self._active_tab else BTN_INACTIVE)
