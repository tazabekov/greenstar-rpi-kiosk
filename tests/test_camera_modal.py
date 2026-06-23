import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PyQt5.QtWidgets import QLabel, QPushButton

from ui.widgets.camera_modal import CameraModal
from ui.header import HeaderWidget


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
        modal.close()
        assert modal._cam is None


class TestHeaderCameraButton:
    def test_show_camera_button_increases_layout_count(self, qtbot):
        header = HeaderWidget()
        qtbot.addWidget(header)
        count_before = header.layout().count()
        header.show_camera_button()
        assert header.layout().count() == count_before + 1

    def test_camera_button_emits_cameras_requested(self, qtbot):
        header = HeaderWidget()
        qtbot.addWidget(header)
        header.show_camera_button()
        received = []
        header.cameras_requested.connect(lambda: received.append(True))
        # find the camera button by text
        cam_btn = None
        for i in range(header.layout().count()):
            item = header.layout().itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, QPushButton) and w.text() == "\U0001f4f7":
                cam_btn = w
                break
        assert cam_btn is not None, "Camera button not found in header layout"
        cam_btn.click()
        assert received == [True]

    def test_camera_button_inserted_before_gear(self, qtbot):
        header = HeaderWidget()
        qtbot.addWidget(header)
        gear_idx = header.layout().indexOf(header._gear)
        header.show_camera_button()
        cam_btn = None
        for i in range(header.layout().count()):
            item = header.layout().itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, QPushButton) and w.text() == "\U0001f4f7":
                cam_btn = w
                break
        cam_idx = header.layout().indexOf(cam_btn)
        new_gear_idx = header.layout().indexOf(header._gear)
        assert cam_idx == new_gear_idx - 1
