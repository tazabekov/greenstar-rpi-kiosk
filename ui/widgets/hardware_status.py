from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QPen, QColor, QFont
from PyQt5.QtWidgets import QWidget, QHBoxLayout

from ui.theme import PANEL_BG, BORDER_DIM, TEXT_MID, TEXT_DIM, ACCENT_GREEN

_AMBER = QColor("#f0a000")
_RED   = QColor("#ff2244")

# (bit-index, display-label, color) for bits that reflect *current* state
_CURRENT_FLAGS = [
    (0, "UV!",  _RED),
    (1, "CAP",  _AMBER),
    (2, "HOT!", _RED),
    (3, "WARM", _AMBER),
]

# (bit-index, display-label) for bits that reflect *historical* (since-boot) state
_BOOT_FLAGS = [
    (16, "UV"),
    (17, "CAP"),
    (18, "HOT"),
    (19, "WARM"),
]

_FAN_MAX = 7   # RPi 5 official active cooler: cur_state range 0–7


class _ThrottlePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bitmask = 0

    def update_value(self, bitmask):
        self._bitmask = bitmask
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, PANEL_BG)
        painter.fillRect(0, 0, 3, h, BORDER_DIM)
        painter.setPen(QPen(BORDER_DIM, 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        pad = 8

        painter.setFont(QFont("DejaVu Sans", 8))
        painter.setPen(QPen(TEXT_MID))
        painter.drawText(pad + 4, 4, w - pad * 2, 14,
                         Qt.AlignLeft | Qt.AlignTop, "THROTTLE")

        current_active = [(label, color)
                          for bit, label, color in _CURRENT_FLAGS
                          if self._bitmask & (1 << bit)]
        boot_active    = [label
                          for bit, label in _BOOT_FLAGS
                          if self._bitmask & (1 << bit)]

        if not current_active:
            painter.setFont(QFont("DejaVu Sans", 13, QFont.Bold))
            painter.setPen(QPen(ACCENT_GREEN))
            painter.drawText(pad, 18, w - pad * 2, 24,
                             Qt.AlignLeft | Qt.AlignVCenter, "● OK")
        else:
            status_text = "⚠ " + "  ".join(label for label, _ in current_active)
            _, color = current_active[0]
            painter.setFont(QFont("DejaVu Sans", 13, QFont.Bold))
            painter.setPen(QPen(color))
            painter.drawText(pad, 18, w - pad * 2, 22,
                             Qt.AlignLeft | Qt.AlignVCenter, status_text)

        if boot_active:
            painter.setFont(QFont("DejaVu Sans", 7))
            painter.setPen(QPen(TEXT_DIM))
            painter.drawText(pad + 4, 42, w - pad * 2, 14,
                             Qt.AlignLeft | Qt.AlignTop,
                             "boot: " + " ".join(boot_active))

        painter.end()


class _FanPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = -1

    def update_value(self, level):
        self._level = level
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, PANEL_BG)
        painter.fillRect(0, 0, 3, h, BORDER_DIM)
        painter.setPen(QPen(BORDER_DIM, 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        pad = 8

        painter.setFont(QFont("DejaVu Sans", 8))
        painter.setPen(QPen(TEXT_MID))
        painter.drawText(pad + 4, 4, w - pad * 2, 14,
                         Qt.AlignLeft | Qt.AlignTop, "FAN")

        if self._level < 0:
            painter.setFont(QFont("DejaVu Sans", 11))
            painter.setPen(QPen(TEXT_DIM))
            painter.drawText(pad, 18, w - pad * 2, 24,
                             Qt.AlignLeft | Qt.AlignVCenter, "N/A")
        else:
            painter.setFont(QFont("DejaVu Sans", 13, QFont.Bold))
            painter.setPen(QPen(ACCENT_GREEN))
            painter.drawText(pad, 18, w - pad * 2, 22,
                             Qt.AlignLeft | Qt.AlignVCenter,
                             f"Level {self._level}/{_FAN_MAX}")

            bar_x, bar_y = pad + 4, 42
            bar_w = w - pad * 2 - 8
            bar_h = 10
            ratio = max(0.0, min(1.0, self._level / _FAN_MAX))

            bg = QColor(ACCENT_GREEN)
            bg.setAlpha(25)
            painter.setBrush(bg)
            painter.setPen(QPen(Qt.NoPen))
            painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 4, 4)

            if ratio > 0:
                fill = QColor(ACCENT_GREEN)
                fill.setAlpha(200)
                painter.setBrush(fill)
                painter.drawRoundedRect(bar_x, bar_y, int(bar_w * ratio), bar_h, 4, 4)

        painter.end()


class _DiskPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._percent = 0.0

    def update_value(self, percent):
        self._percent = percent
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, PANEL_BG)
        painter.fillRect(0, 0, 3, h, BORDER_DIM)
        painter.setPen(QPen(BORDER_DIM, 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        pad = 8
        color = (_RED   if self._percent >= 90 else
                 _AMBER if self._percent >= 75 else
                 ACCENT_GREEN)

        painter.setFont(QFont("DejaVu Sans", 8))
        painter.setPen(QPen(TEXT_MID))
        painter.drawText(pad + 4, 4, w - pad * 2, 14,
                         Qt.AlignLeft | Qt.AlignTop, "DISK")

        painter.setFont(QFont("DejaVu Sans", 13, QFont.Bold))
        painter.setPen(QPen(color))
        painter.drawText(pad, 18, w - pad * 2, 22,
                         Qt.AlignLeft | Qt.AlignVCenter,
                         f"{self._percent:.1f}%")

        bar_x, bar_y = pad + 4, 42
        bar_w = w - pad * 2 - 8
        bar_h = 10
        ratio = max(0.0, min(1.0, self._percent / 100.0))

        bg = QColor(color)
        bg.setAlpha(25)
        painter.setBrush(bg)
        painter.setPen(QPen(Qt.NoPen))
        painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 4, 4)

        if ratio > 0:
            fill = QColor(color)
            fill.setAlpha(200)
            painter.setBrush(fill)
            painter.drawRoundedRect(bar_x, bar_y, int(bar_w * ratio), bar_h, 4, 4)

        painter.end()


class HardwareStatusBar(QWidget):
    """Three-panel status strip: throttle flags | fan level | disk usage."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._throttle = _ThrottlePanel()
        self._fan      = _FanPanel()
        self._disk     = _DiskPanel()

        layout.addWidget(self._throttle, stretch=1)
        layout.addWidget(self._fan,      stretch=1)
        layout.addWidget(self._disk,     stretch=1)

    def push_throttle(self, bitmask: int):
        self._throttle.update_value(bitmask)

    def push_fan(self, level: int):
        self._fan.update_value(level)

    def push_disk(self, percent: float):
        self._disk.update_value(percent)
