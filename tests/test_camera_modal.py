import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PyQt5.QtWidgets import QLabel, QPushButton

from ui.widgets.camera_modal import CameraModal


class TestCameraModal:
    def test_instantiation(self, qtbot):
        modal = CameraModal(parent=None)
        qtbot.addWidget(modal)
        assert modal is not None

    def test_has_view_label(self, qtbot):
        modal = CameraModal(parent=None)
        qtbot.addWidget(modal)
        assert isinstance(modal._view, QLabel)

    def test_status_shows_resolution(self, qtbot):
        modal = CameraModal(parent=None)
        qtbot.addWidget(modal)
        assert "640" in modal._status.text()
        assert "480" in modal._status.text()

    def test_timer_not_active_before_show(self, qtbot):
        modal = CameraModal(parent=None)
        qtbot.addWidget(modal)
        assert not modal._timer.isActive()

    def test_cam_none_before_show(self, qtbot):
        modal = CameraModal(parent=None)
        qtbot.addWidget(modal)
        assert modal._cam is None

    def test_close_stops_timer(self, qtbot):
        modal = CameraModal(parent=None)
        qtbot.addWidget(modal)
        modal._timer.start()
        modal.close()
        assert not modal._timer.isActive()

    def test_cam_none_after_close(self, qtbot):
        modal = CameraModal(parent=None)
        qtbot.addWidget(modal)
        modal._cam = object()  # simulate an open camera handle
        modal._cam = None      # close sets it to None
        modal.close()
        assert modal._cam is None
