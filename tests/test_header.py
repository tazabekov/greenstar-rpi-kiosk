import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from ui.header import StatusDotButton, HeaderWidget


class TestStatusDotButton:
    def test_renders_without_dot_initially(self, qtbot):
        btn = StatusDotButton("System")
        qtbot.addWidget(btn)
        btn.resize(120, 44)
        btn.show()
        btn.repaint()

    def test_renders_green_dot(self, qtbot):
        btn = StatusDotButton("System")
        qtbot.addWidget(btn)
        btn.resize(120, 44)
        btn.set_health("green")
        btn.show()
        btn.repaint()

    def test_renders_yellow_dot(self, qtbot):
        btn = StatusDotButton("System")
        qtbot.addWidget(btn)
        btn.resize(120, 44)
        btn.set_health("yellow")
        btn.show()
        btn.repaint()

    def test_renders_red_dot(self, qtbot):
        btn = StatusDotButton("System")
        qtbot.addWidget(btn)
        btn.resize(120, 44)
        btn.set_health("red")
        btn.show()
        btn.repaint()

    def test_unknown_color_hides_dot(self, qtbot):
        btn = StatusDotButton("System")
        qtbot.addWidget(btn)
        btn.resize(120, 44)
        btn.set_health("unknown")
        btn.show()
        btn.repaint()


class TestHeaderWidgetSystemHealth:
    def test_update_system_health_green(self, qtbot):
        header = HeaderWidget()
        qtbot.addWidget(header)
        header.resize(800, 64)
        header.show()
        header.update_system_health("green", "All systems OK")

    def test_update_system_health_yellow(self, qtbot):
        header = HeaderWidget()
        qtbot.addWidget(header)
        header.resize(800, 64)
        header.show()
        header.update_system_health("yellow", "Camera offline")

    def test_update_system_health_red(self, qtbot):
        header = HeaderWidget()
        qtbot.addWidget(header)
        header.resize(800, 64)
        header.show()
        header.update_system_health("red", "Firestore write failed")
