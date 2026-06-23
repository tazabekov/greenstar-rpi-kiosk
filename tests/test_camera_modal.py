import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock
from PyQt5.QtWidgets import QTabWidget

from core.camera_registry import CameraInfo
from ui.widgets.camera_modal import CameraModal


def _info(idx=0, model="ov5647", max_w=2592, max_h=1944):
    return CameraInfo(idx=idx, model=model, max_w=max_w, max_h=max_h)


class TestCameraModalLayout:
    def test_no_cameras_no_panels(self, qtbot):
        with patch("core.camera_registry.registry") as reg:
            reg.cameras.return_value = []
            modal = CameraModal()
            qtbot.addWidget(modal)
        assert modal._panels == []

    def test_single_camera_one_panel(self, qtbot):
        with patch("core.camera_registry.registry") as reg:
            reg.cameras.return_value = [_info(0)]
            modal = CameraModal()
            qtbot.addWidget(modal)
        assert len(modal._panels) == 1

    def test_two_cameras_two_panels_no_tabs(self, qtbot):
        with patch("core.camera_registry.registry") as reg:
            reg.cameras.return_value = [_info(0), _info(1, "imx219", 3280, 2464)]
            modal = CameraModal()
            qtbot.addWidget(modal)
        assert len(modal._panels) == 2
        assert modal.findChild(QTabWidget) is None

    def test_three_cameras_uses_tab_widget(self, qtbot):
        with patch("core.camera_registry.registry") as reg:
            reg.cameras.return_value = [
                _info(0), _info(1, "imx219", 3280, 2464), _info(2, "imx477", 4056, 3040)
            ]
            modal = CameraModal()
            qtbot.addWidget(modal)
        assert len(modal._panels) == 3
        tabs = modal.findChild(QTabWidget)
        assert tabs is not None
        assert tabs.count() == 3


class TestCameraFeedPanel:
    def test_status_initially_empty(self, qtbot):
        panel = CameraModal._CameraFeedPanel(_info())
        qtbot.addWidget(panel)
        assert panel._status.text() == ""

    def test_running_false_initially(self, qtbot):
        panel = CameraModal._CameraFeedPanel(_info())
        qtbot.addWidget(panel)
        assert panel._running is False

    def test_cam_none_initially(self, qtbot):
        panel = CameraModal._CameraFeedPanel(_info())
        qtbot.addWidget(panel)
        assert panel._cam is None

    def test_stop_sets_running_false(self, qtbot):
        panel = CameraModal._CameraFeedPanel(_info())
        qtbot.addWidget(panel)
        panel._running = True
        panel._cam = MagicMock()
        with patch("core.camera_registry.registry"):
            panel.stop()
        assert panel._running is False
        assert panel._cam is None

    def test_stop_safe_when_cam_none(self, qtbot):
        panel = CameraModal._CameraFeedPanel(_info())
        qtbot.addWidget(panel)
        panel.stop()   # must not raise


class TestHeaderQuitButton:
    def test_quit_button_present(self, qtbot):
        from ui.header import HeaderWidget
        header = HeaderWidget()
        qtbot.addWidget(header)
        assert header._quit_btn is not None

    def test_quit_button_emits_signal(self, qtbot):
        from ui.header import HeaderWidget
        header = HeaderWidget()
        qtbot.addWidget(header)
        received = []
        header.quit_requested.connect(lambda: received.append(True))
        header._quit_btn.clicked.emit()
        assert received == [True]
