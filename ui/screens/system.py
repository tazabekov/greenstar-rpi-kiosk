from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from ui.theme import ACCENT_GREEN, WINDOWS, BTN_ACTIVE, BTN_INACTIVE
from ui.widgets.graph import GraphWidget
from ui.widgets.hardware_status import HardwareStatusBar

_DEFAULT_WINDOW = "5 min"

_HEALTH_SYMBOL = {"green": "●", "yellow": "⚠", "red": "✕"}
_HEALTH_STYLE = {
    "green":  "color: #39ff14; font-size: 10pt; padding-left: 4px; border: none;",
    "yellow": "color: #f0a000; font-size: 10pt; padding-left: 4px; border: none;",
    "red":    "color: #ff2244; font-size: 10pt; padding-left: 4px; border: none;",
}


class SystemScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_window = _DEFAULT_WINDOW

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(8)

        self._status_label = QLabel("● Waiting…")
        self._status_label.setFixedHeight(22)
        self._status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._status_label.setStyleSheet(
            "color: #555555; font-size: 10pt; padding-left: 4px; border: none;"
        )
        root.addWidget(self._status_label)

        self.cpu_graph = GraphWidget(
            "CPU Usage", "%", ACCENT_GREEN,
            min_span=20, anchor_zero=True,
        )
        # Temperature: cold colour used for area fill; line segments are
        # heat-mapped green → amber → red via _temp_color().
        self.temp_graph = GraphWidget(
            "CPU Temperature", "°C", QColor("#39ff14"),
            min_span=20, heat_color=True,
        )
        root.addWidget(self.cpu_graph, stretch=1)
        root.addWidget(self.temp_graph, stretch=1)

        self.hw_status = HardwareStatusBar()
        self.hw_status.setFixedHeight(60)
        root.addWidget(self.hw_status)

        # Time-window button bar
        bar = QWidget()
        bar.setFixedHeight(70)
        bar.setStyleSheet("background-color: #0a0a0a; border-top: 2px solid #1a5c08;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(12)

        self._window_buttons = {}
        for label, _ in WINDOWS:
            btn = QPushButton(label)
            btn.setFixedHeight(52)
            btn.setMinimumWidth(90)
            btn.clicked.connect(lambda _, l=label: self._select_window(l))
            bl.addWidget(btn)
            self._window_buttons[label] = btn

        root.addWidget(bar)
        self._apply_styles(_DEFAULT_WINDOW)

    def _disable_graph_updates(self):
        """Disable updates on painted children to prevent ARM/Xwayland teardown
        repaints from crashing (SIGBUS/SIGSEGV)."""
        self.cpu_graph.setUpdatesEnabled(False)
        self.temp_graph.setUpdatesEnabled(False)

    def hideEvent(self, event):
        self._disable_graph_updates()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._disable_graph_updates()
        super().closeEvent(event)

    def wire_sampler(self, sampler):
        """Connect DataSampler signals. Called by MainWindow after construction."""
        sampler.cpu_sample.connect(self.cpu_graph.push)
        sampler.temp_sample.connect(self.temp_graph.push)
        sampler.fan_sample.connect(self.hw_status.push_fan)
        sampler.disk_sample.connect(self.hw_status.push_disk)
        sampler.throttle_sample.connect(self.hw_status.push_throttle)

    def _select_window(self, label):
        if label == self._active_window:
            return
        self._active_window = label
        self._apply_styles(label)
        n = dict(WINDOWS)[label]
        self.cpu_graph.set_window(n)
        self.temp_graph.set_window(n)

    def _apply_styles(self, active):
        for label, btn in self._window_buttons.items():
            btn.setStyleSheet(BTN_ACTIVE if label == active else BTN_INACTIVE)

    @pyqtSlot(str, str)
    def update_health(self, color: str, reason: str):
        symbol = _HEALTH_SYMBOL.get(color, "●")
        self._status_label.setText(f"{symbol} {reason}")
        self._status_label.setStyleSheet(
            _HEALTH_STYLE.get(color, _HEALTH_STYLE["green"])
        )
