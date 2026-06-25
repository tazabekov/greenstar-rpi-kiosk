import math
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal, pyqtSlot
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
        painter.setPen(QPen(Qt.NoPen))
        painter.drawEllipse(QPointF(cx, cy), r_outer + 4, r_outer + 4)
        painter.setBrush(QColor("#39ff14"))
        painter.setPen(QPen(Qt.NoPen))
        painter.drawPath(path)


class CameraIcon(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(44, 44)
        self._hovered = False
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        col = QColor("#39ff14") if self._hovered else QColor("#555555")
        p.setPen(QPen(Qt.NoPen))
        w, h = self.width(), self.height()
        # camera body
        bx, by, bw, bh = w * 0.14, h * 0.42, w * 0.72, h * 0.36
        p.setBrush(col)
        p.drawRoundedRect(QRectF(bx, by, bw, bh), 3, 3)
        # viewfinder bump on top
        vw, vh = bw * 0.28, h * 0.12
        p.drawRoundedRect(QRectF(w / 2 - vw / 2, by - vh, vw, vh), 2, 2)
        # lens dark ring
        cx, cy = w / 2, by + bh * 0.52
        ro = bh * 0.42
        p.setBrush(QColor("#0d0d0d"))
        p.drawEllipse(QPointF(cx, cy), ro, ro)
        # lens highlight
        p.setBrush(col)
        p.drawEllipse(QPointF(cx, cy), ro * 0.55, ro * 0.55)

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class StatusDotButton(QPushButton):
    """QPushButton that overlays a small health-status dot in the top-right corner."""

    _DOT_R = 6
    _DOT_COLORS = {
        "green":  QColor("#39ff14"),
        "yellow": QColor("#f0a000"),
        "red":    QColor("#ff2244"),
    }

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._dot_color = None

    def set_health(self, color: str):
        self._dot_color = self._DOT_COLORS.get(color)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._dot_color is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._DOT_R
        x = self.width() - r - 5
        y = r + 4
        p.setPen(QPen(Qt.NoPen))
        p.setBrush(QColor("#0d0d0d"))
        p.drawEllipse(QPointF(x, y), r + 1.5, r + 1.5)
        p.setBrush(self._dot_color)
        p.drawEllipse(QPointF(x, y), float(r), float(r))
        p.end()


class HeaderWidget(QWidget):
    tab_changed        = pyqtSignal(str)   # "dashboard" | "system"
    settings_requested = pyqtSignal()
    cameras_requested  = pyqtSignal()
    quit_requested     = pyqtSignal()

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
            btn = StatusDotButton(label) if key == "system" else QPushButton(label)
            btn.setFixedHeight(44)
            btn.setMinimumWidth(110)
            btn.clicked.connect(lambda _, k=key: self._on_tab(k))
            layout.addWidget(btn)
            self._tab_buttons[key] = btn

        layout.addSpacing(8)

        self._gear = QPushButton("⚙")
        self._gear.setFixedSize(44, 44)
        self._gear.setStyleSheet(
            "QPushButton { background-color: transparent; color: #555555;"
            " border: none; font-size: 18pt; }"
            " QPushButton:hover { color: #39ff14; }"
            " QPushButton:pressed { color: #e8e8e8; }"
        )
        self._gear.clicked.connect(self.settings_requested)
        layout.addWidget(self._gear)

        layout.addSpacing(4)

        self._clock = QLabel()
        self._clock.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._clock.setStyleSheet("border: none;")
        layout.addWidget(self._clock)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

        layout.addSpacing(8)

        self._quit_btn = QPushButton("✕")
        self._quit_btn.setFixedSize(44, 44)
        self._quit_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #555555;"
            " border: none; font-size: 16pt; }"
            " QPushButton:hover { color: #cc3333; }"
            " QPushButton:pressed { color: #ff4444; }"
        )
        self._quit_btn.clicked.connect(self.quit_requested)
        layout.addWidget(self._quit_btn)

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

    def show_camera_button(self):
        cam_btn = CameraIcon()
        cam_btn.clicked.connect(self.cameras_requested)
        idx = self.layout().indexOf(self._gear)
        self.layout().insertWidget(idx, cam_btn)

    def _shutdown(self):
        """Stop timer and disable updates to prevent ARM/Xwayland teardown
        repaints from crashing (SIGBUS/SIGSEGV)."""
        self._timer.stop()
        self.setUpdatesEnabled(False)

    def hideEvent(self, event):
        self._shutdown()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._shutdown()
        super().closeEvent(event)

    @pyqtSlot(str, str)
    def update_system_health(self, color: str, reason: str):
        self._tab_buttons["system"].set_health(color)
