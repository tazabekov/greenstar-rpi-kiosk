import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from ui.screens.system import SystemScreen


class TestSystemScreenHealthRow:
    def test_renders_initial_waiting_state(self, qtbot):
        screen = SystemScreen()
        qtbot.addWidget(screen)
        screen.resize(800, 416)
        screen.show()
        screen.repaint()

    def test_update_health_green(self, qtbot):
        screen = SystemScreen()
        qtbot.addWidget(screen)
        screen.resize(800, 416)
        screen.update_health("green", "All systems OK")
        screen.show()
        screen.repaint()
        assert "All systems OK" in screen._status_label.text()

    def test_update_health_yellow(self, qtbot):
        screen = SystemScreen()
        qtbot.addWidget(screen)
        screen.resize(800, 416)
        screen.update_health("yellow", "Camera offline")
        screen.show()
        screen.repaint()
        assert "Camera offline" in screen._status_label.text()

    def test_update_health_red(self, qtbot):
        screen = SystemScreen()
        qtbot.addWidget(screen)
        screen.resize(800, 416)
        screen.update_health("red", "Firestore write failed")
        screen.show()
        screen.repaint()
        assert "Firestore write failed" in screen._status_label.text()

    def test_symbol_changes_with_color(self, qtbot):
        screen = SystemScreen()
        qtbot.addWidget(screen)
        screen.resize(800, 416)
        screen.update_health("yellow", "Camera offline")
        assert "⚠" in screen._status_label.text()
        screen.update_health("red", "Firestore write failed")
        assert "✕" in screen._status_label.text()
        screen.update_health("green", "All systems OK")
        assert "●" in screen._status_label.text()
