import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from core.health import HealthMonitor


def _collect(monitor, qtbot):
    """Helper: return list to capture health_changed emissions."""
    received = []
    monitor.health_changed.connect(lambda c, r: received.append((c, r)))
    return received


class TestHealthMonitorGreen:
    def test_default_all_clear_after_first_update(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(0.0)
        assert received[-1][0] == "green"

    def test_cpu_below_threshold_is_green(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(84.9)
        assert received[-1][0] == "green"

    def test_temp_below_threshold_is_green(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_temp(69.9)
        assert received[-1][0] == "green"

    def test_disk_below_threshold_is_green(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_disk(74.9)
        assert received[-1][0] == "green"

    def test_throttle_boot_only_flags_is_green(self, qtbot):
        """Bits 16-19 are historical-only; no current throttle → green."""
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_throttle(0xF0000)
        assert received[-1][0] == "green"

    def test_reason_is_all_systems_ok_when_green(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(10.0)
        assert "OK" in received[-1][1] or "ok" in received[-1][1].lower()


class TestHealthMonitorYellow:
    def test_cpu_at_threshold_is_yellow(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(85.0)
        assert received[-1][0] == "yellow"

    def test_cpu_above_threshold_is_yellow(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(90.0)
        assert received[-1][0] == "yellow"

    def test_temp_at_threshold_is_yellow(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_temp(70.0)
        assert received[-1][0] == "yellow"

    def test_disk_at_threshold_is_yellow(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_disk(75.0)
        assert received[-1][0] == "yellow"

    def test_throttle_current_flags_is_yellow(self, qtbot):
        """Bits 0-3 are current throttle flags."""
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_throttle(0x000F)
        assert received[-1][0] == "yellow"

    def test_throttle_single_current_flag_is_yellow(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_throttle(0x0001)
        assert received[-1][0] == "yellow"

    def test_camera_offline_is_yellow(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_camera_ok(False)
        assert received[-1][0] == "yellow"

    def test_camera_online_is_green(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_camera_ok(True)
        assert received[-1][0] == "green"

    def test_reason_contains_cpu_value(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(90.0)
        assert "90" in received[-1][1]

    def test_reason_contains_temp_value(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_temp(72.0)
        assert "72" in received[-1][1]

    def test_reason_contains_disk_value(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_disk(80.0)
        assert "80" in received[-1][1]


class TestHealthMonitorRed:
    def test_firestore_failure_is_red(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_firestore_ok(False)
        assert received[-1][0] == "red"

    def test_firestore_recovery_returns_to_green(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_firestore_ok(False)
        monitor.on_firestore_ok(True)
        assert received[-1][0] == "green"

    def test_red_overrides_yellow(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(90.0)        # would be yellow
        monitor.on_firestore_ok(False)
        assert received[-1][0] == "red"

    def test_reason_mentions_firestore(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_firestore_ok(False)
        assert "firestore" in received[-1][1].lower() or "write" in received[-1][1].lower()


class TestHealthMonitorEmissionBehavior:
    def test_emits_on_every_slot_call(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(10.0)
        monitor.on_cpu(11.0)
        assert len(received) >= 2

    def test_all_slots_trigger_emission(self, qtbot):
        monitor = HealthMonitor()
        received = _collect(monitor, qtbot)
        monitor.on_cpu(0.0)
        monitor.on_temp(0.0)
        monitor.on_disk(0.0)
        monitor.on_throttle(0)
        monitor.on_camera_ok(True)
        monitor.on_firestore_ok(True)
        assert len(received) == 6
