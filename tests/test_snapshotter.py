"""
Tests for Snapshotter and the Settings modal snapshot interval field.

These tests run without real hardware or Firebase — they patch
at the sys.modules level so no import errors occur on non-Pi machines.
"""
import os
import sys
import types
import unittest.mock as mock

import pytest
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication


# ---------------------------------------------------------------------------
# Minimal stubs for modules that may not be present in CI
# ---------------------------------------------------------------------------

def _install_firebase_stub():
    """Install lightweight firebase_admin stub into sys.modules."""
    if "firebase_admin" in sys.modules:
        return

    pkg = types.ModuleType("firebase_admin")
    pkg._apps = {}

    fs_mod = types.ModuleType("firebase_admin.firestore")
    fs_mod.SERVER_TIMESTAMP = "SERVER_TIMESTAMP"

    class _FakeClient:
        def collection(self, name):
            return _FakeCollection()

    class _FakeCollection:
        def document(self, doc_id):
            return _FakeDocRef()

    class _FakeDocRef:
        def update(self, data):
            pass

    fs_mod.client = lambda: _FakeClient()

    st_mod = types.ModuleType("firebase_admin.storage")

    class _FakeBucket:
        def blob(self, path):
            return _FakeBlob()

    class _FakeBlob:
        def upload_from_filename(self, path, content_type=None):
            pass

    st_mod.bucket = lambda name: _FakeBucket()

    pkg.firestore = fs_mod
    pkg.storage = st_mod

    sys.modules["firebase_admin"] = pkg
    sys.modules["firebase_admin.firestore"] = fs_mod
    sys.modules["firebase_admin.storage"] = st_mod


_install_firebase_stub()

from core.snapshotter import Snapshotter  # noqa: E402 (after stubs installed)
from core.bus import bus  # noqa: E402


# ---------------------------------------------------------------------------
# Snapshotter unit tests
# ---------------------------------------------------------------------------

class TestSnapshotterInit:
    def test_instantiates_without_errors(self, qtbot):
        s = Snapshotter()
        assert s is not None

    def test_timer_not_running_before_start(self, qtbot):
        s = Snapshotter()
        assert not s._timer.isActive()

    def test_stop_is_safe_before_start(self, qtbot):
        s = Snapshotter()
        s.stop()  # must not raise


class TestSnapshotterStart:
    def test_start_without_firebase_apps_does_not_raise(self, qtbot, monkeypatch):
        import firebase_admin
        monkeypatch.setattr(firebase_admin, "_apps", {}, raising=False)
        monkeypatch.setenv("GKM_FIREBASE_STORAGE_BUCKET", "")
        s = Snapshotter()
        s.start()  # should log warning and return without raising
        assert not s._timer.isActive()

    def test_start_without_bucket_env_leaves_timer_inactive(self, qtbot, monkeypatch):
        monkeypatch.delenv("GKM_FIREBASE_STORAGE_BUCKET", raising=False)
        s = Snapshotter()
        s.start()
        assert not s._timer.isActive()


class TestSnapshotterSetInterval:
    def _make_started(self, monkeypatch):
        """Return a Snapshotter with _kiosk_ref mocked so _schedule works."""
        s = Snapshotter()
        s._kiosk_ref = mock.MagicMock()
        return s

    def test_set_interval_zero_leaves_timer_inactive(self, qtbot, monkeypatch):
        s = self._make_started(monkeypatch)
        s.set_interval(0)
        assert not s._timer.isActive()

    def test_set_interval_positive_starts_timer(self, qtbot, monkeypatch):
        s = self._make_started(monkeypatch)
        s.set_interval(5)
        assert s._timer.isActive()
        s.stop()

    def test_set_interval_writes_env(self, qtbot, monkeypatch, tmp_path):
        s = self._make_started(monkeypatch)
        monkeypatch.delenv("GKM_SNAPSHOT_INTERVAL_MIN", raising=False)
        s.set_interval(3)
        assert os.environ.get("GKM_SNAPSHOT_INTERVAL_MIN") == "3"
        s.stop()

    def test_set_interval_zero_stops_active_timer(self, qtbot, monkeypatch):
        s = self._make_started(monkeypatch)
        s.set_interval(5)
        assert s._timer.isActive()
        s.set_interval(0)
        assert not s._timer.isActive()


class TestSnapshotterSchedule:
    def test_schedule_noop_when_interval_zero(self, qtbot):
        s = Snapshotter()
        s._interval_min = 0
        s._kiosk_ref = mock.MagicMock()
        s._schedule()
        assert not s._timer.isActive()

    def test_schedule_noop_when_no_kiosk_ref(self, qtbot):
        s = Snapshotter()
        s._interval_min = 5
        s._kiosk_ref = None
        s._schedule()
        assert not s._timer.isActive()

    def test_schedule_starts_timer_when_configured(self, qtbot):
        s = Snapshotter()
        s._interval_min = 2
        s._kiosk_ref = mock.MagicMock()
        s._schedule()
        assert s._timer.isActive()
        s.stop()


class TestSnapshotterCaptureJpeg:
    def _make_info(self, idx=0):
        from core.camera_registry import CameraInfo
        return CameraInfo(idx=idx, model="ov5647", max_w=2592, max_h=1944)

    def test_capture_returns_none_when_picamera2_unavailable(self, qtbot, monkeypatch):
        """_capture_jpeg returns None when picamera2 raises on construction."""
        broken = types.ModuleType("picamera2")

        class _BrokenCam:
            def __init__(self, *a, **kw):
                raise RuntimeError("no camera hardware")

        broken.Picamera2 = _BrokenCam
        monkeypatch.setitem(sys.modules, "picamera2", broken)

        import core.camera_registry as _reg_mod
        mock_reg = mock.MagicMock()
        mock_reg.acquire.return_value = True
        monkeypatch.setattr(_reg_mod, "registry", mock_reg)

        s = Snapshotter()
        result = s._capture_jpeg(self._make_info())
        assert result is None

    def test_capture_cleans_up_temp_file_on_error(self, qtbot, monkeypatch, tmp_path):
        """Temp file is deleted even when capture raises."""
        created = []

        def _mkstemp(suffix=""):
            path = str(tmp_path / "snap.jpg")
            open(path, "w").close()
            created.append(path)
            import os as _os
            fd = _os.open(path, _os.O_RDWR)
            return fd, path

        monkeypatch.setattr("tempfile.mkstemp", _mkstemp)

        broken = types.ModuleType("picamera2")

        class _BrokenCam:
            def __init__(self, *a, **kw):
                raise RuntimeError("no hardware")

        broken.Picamera2 = _BrokenCam
        monkeypatch.setitem(sys.modules, "picamera2", broken)

        import core.camera_registry as _reg_mod
        mock_reg = mock.MagicMock()
        mock_reg.acquire.return_value = True
        monkeypatch.setattr(_reg_mod, "registry", mock_reg)

        s = Snapshotter()
        result = s._capture_jpeg(self._make_info())
        assert result is None
        for p in created:
            assert not os.path.exists(p), "temp file was not cleaned up"

    def test_capture_skips_when_camera_locked(self, qtbot, monkeypatch):
        """_capture_jpeg returns None immediately when registry.acquire returns False."""
        import core.camera_registry as _reg_mod
        mock_reg = mock.MagicMock()
        mock_reg.acquire.return_value = False
        monkeypatch.setattr(_reg_mod, "registry", mock_reg)

        s = Snapshotter()
        result = s._capture_jpeg(self._make_info())
        assert result is None


class TestSnapshotterBusSignal:
    def test_set_interval_slot_receives_bus_signal(self, qtbot, monkeypatch):
        s = Snapshotter()
        s._kiosk_ref = mock.MagicMock()

        received = []
        original = s.set_interval

        def _spy(n):
            received.append(n)
            original(n)

        s.set_interval = _spy
        bus.snapshot_interval_changed.connect(s.set_interval)

        try:
            bus.snapshot_interval_changed.emit(7)
            assert received == [7]
        finally:
            bus.snapshot_interval_changed.disconnect(s.set_interval)
            s.stop()


# ---------------------------------------------------------------------------
# SettingsModal snapshot interval field tests
# ---------------------------------------------------------------------------

class TestSettingsModalSnapshotField:
    def test_field_loads_from_env(self, qtbot, monkeypatch):
        monkeypatch.setenv("GKM_SNAPSHOT_INTERVAL_MIN", "15")
        from ui.widgets.settings_modal import SettingsModal
        modal = SettingsModal()
        qtbot.addWidget(modal)
        assert modal._snap_edit.text() == "15"

    def test_field_defaults_to_zero(self, qtbot, monkeypatch):
        monkeypatch.delenv("GKM_SNAPSHOT_INTERVAL_MIN", raising=False)
        from ui.widgets.settings_modal import SettingsModal
        modal = SettingsModal()
        qtbot.addWidget(modal)
        assert modal._snap_edit.text() == "0"

    def test_save_emits_snapshot_interval_changed(self, qtbot, monkeypatch, tmp_path):
        # Point set_key at a temp .env so we don't modify the real one
        fake_env = tmp_path / ".env"
        fake_env.write_text("")
        monkeypatch.setenv("GKM_SNAPSHOT_INTERVAL_MIN", "0")

        import ui.widgets.settings_modal as sm_mod
        monkeypatch.setattr(sm_mod, "_ENV_PATH", str(fake_env))

        from ui.widgets.settings_modal import SettingsModal
        modal = SettingsModal()
        qtbot.addWidget(modal)

        modal._snap_edit.setText("10")
        modal._name_edit.setText("Test Kiosk")
        modal._loc_edit.setText("Test City")
        modal._id_edit.setText("test-id")

        with qtbot.waitSignal(bus.snapshot_interval_changed, timeout=1000) as sig:
            modal._save()

        assert sig.args == [10]
