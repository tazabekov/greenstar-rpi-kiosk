"""
Shared fixtures for the greenstar-rpi-kiosk test suite.
"""
import os
import sys

# Must be set before any Qt imports so Xwayland can find the display.
os.environ.setdefault("DISPLAY", ":0")

# Make the project root importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PyQt5.QtWidgets import QApplication


# pytest-qt provides the `qtbot` fixture automatically when qt_api = pyqt5
# is declared in pytest.ini.  Nothing extra is needed here for basic widget
# tests, but we add a convenience fixture for callers that need a bare
# QApplication without qtbot.

@pytest.fixture(scope="session")
def qapp_instance():
    """Session-scoped QApplication (pytest-qt creates one automatically, but
    this fixture lets non-widget tests reuse the same instance)."""
    app = QApplication.instance() or QApplication(sys.argv)
    return app


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_teardown(item, nextitem):
    """Hide all visible top-level Qt widgets before pytestqt processes pending
    paint events.  On ARM/Xwayland the teardown paint can crash (SIGBUS/SIGSEGV)
    if painted widgets are still visible when QApplication.processEvents() fires.
    Using wrapper=True + tryfirst=True makes us the outermost wrapper so we run
    before pytestqt's trylast wrapper."""
    app = QApplication.instance()
    if app is not None:
        for widget in app.topLevelWidgets():
            if widget.isVisible():
                widget.hide()
    return (yield)
