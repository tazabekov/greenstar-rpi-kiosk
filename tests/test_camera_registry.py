import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch

from core.camera_registry import CameraInfo, CameraRegistry


def _mock_picamera2(cameras):
    """Return a mock Picamera2 class for the given list of (idx, model, w, h) tuples."""
    instances = {
        idx: MagicMock(camera_properties={"PixelArraySize": (w, h)})
        for idx, model, w, h in cameras
    }
    klass = MagicMock()
    klass.global_camera_info.return_value = [
        {"Num": idx, "Model": model} for idx, model, w, h in cameras
    ]
    klass.side_effect = lambda i: instances[i]
    return klass


class TestCameraRegistry:
    def test_probe_one_camera(self):
        reg = CameraRegistry()
        mock_cam = _mock_picamera2([(0, "ov5647", 2592, 1944)])
        with patch.dict("sys.modules", {"picamera2": MagicMock(Picamera2=mock_cam)}):
            reg.probe()
        assert reg.cameras() == [CameraInfo(idx=0, model="ov5647", max_w=2592, max_h=1944)]

    def test_probe_two_cameras(self):
        reg = CameraRegistry()
        mock_cam = _mock_picamera2([
            (0, "ov5647", 2592, 1944),
            (1, "imx219", 3280, 2464),
        ])
        with patch.dict("sys.modules", {"picamera2": MagicMock(Picamera2=mock_cam)}):
            reg.probe()
        cams = reg.cameras()
        assert len(cams) == 2
        assert cams[1] == CameraInfo(idx=1, model="imx219", max_w=3280, max_h=2464)

    def test_per_camera_locks_are_independent(self):
        reg = CameraRegistry()
        mock_cam = _mock_picamera2([
            (0, "ov5647", 2592, 1944),
            (1, "imx219", 3280, 2464),
        ])
        with patch.dict("sys.modules", {"picamera2": MagicMock(Picamera2=mock_cam)}):
            reg.probe()
        assert reg.acquire(0) is True
        assert reg.acquire(1) is True   # camera 1 unaffected by camera 0 lock
        reg.release(0)
        reg.release(1)

    def test_acquire_already_locked_returns_false(self):
        reg = CameraRegistry()
        mock_cam = _mock_picamera2([(0, "ov5647", 2592, 1944)])
        with patch.dict("sys.modules", {"picamera2": MagicMock(Picamera2=mock_cam)}):
            reg.probe()
        assert reg.acquire(0) is True
        assert reg.acquire(0) is False   # already held, non-blocking
        reg.release(0)

    def test_probe_no_picamera2(self):
        reg = CameraRegistry()
        with patch.dict("sys.modules", {"picamera2": None}):
            reg.probe()   # must not raise
        assert reg.cameras() == []
