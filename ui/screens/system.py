from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel

from ui.theme import ACCENT_GREEN, TEMP_LINE, INTERVALS, BTN_ACTIVE, BTN_INACTIVE
from ui.widgets.graph import GraphWidget


class SystemScreen(QWidget):
    interval_changed = pyqtSignal(int)   # ms — consumed by MainWindow

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_interval = "1 s"

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(8)

        self.cpu_graph = GraphWidget(
            "CPU Usage", "%", 0, 100, ACCENT_GREEN, [0, 25, 50, 75, 100]
        )
        self.temp_graph = GraphWidget(
            "CPU Temperature", "°C", 30, 85, TEMP_LINE, [30, 45, 60, 75, 85]
        )
        root.addWidget(self.cpu_graph, stretch=1)
        root.addWidget(self.temp_graph, stretch=1)

        # "Showing last X" label above button bar
        self._window_lbl = QLabel("Showing last  1 s")
        self._window_lbl.setStyleSheet(
            "color: #555555; font-size: 9pt; background: transparent;"
            " padding-left: 14px; padding-bottom: 2px;"
        )
        root.addWidget(self._window_lbl)

        # Interval button bar
        bar = QWidget()
        bar.setFixedHeight(70)
        bar.setStyleSheet("background-color: #0a0a0a; border-top: 2px solid #1a5c08;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 8, 12, 8)
        bl.setSpacing(12)

        self._interval_buttons = {}
        for label in INTERVALS:
            btn = QPushButton(label)
            btn.setFixedHeight(52)
            btn.setMinimumWidth(90)
            btn.clicked.connect(lambda _, l=label: self._select_interval(l))
            bl.addWidget(btn)
            self._interval_buttons[label] = btn

        root.addWidget(bar)
        self._apply_styles("1 s")

    def wire_sampler(self, sampler):
        """Connect DataSampler signals. Called by MainWindow after construction."""
        sampler.cpu_sample.connect(self.cpu_graph.push)
        sampler.temp_sample.connect(self.temp_graph.push)

    def _select_interval(self, label):
        if label == self._active_interval:
            return
        self._active_interval = label
        self._apply_styles(label)
        self._window_lbl.setText(f"Showing last  {label}")
        ms = INTERVALS[label]
        self.cpu_graph.interval_ms = ms
        self.temp_graph.interval_ms = ms
        self.interval_changed.emit(ms)

    def _apply_styles(self, active):
        for label, btn in self._interval_buttons.items():
            btn.setStyleSheet(BTN_ACTIVE if label == active else BTN_INACTIVE)
