import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.widgets.hardware_status import HardwareStatusBar


class TestHardwareStatusBarSmoke:
    """Verify the widget renders without crash for all significant states."""

    def test_ok_state(self, qtbot):
        bar = HardwareStatusBar()
        qtbot.addWidget(bar)
        bar.resize(800, 60)
        bar.push_throttle(0)
        bar.push_fan(0)
        bar.push_disk(30.0)
        bar.show()
        bar.repaint()

    def test_all_current_throttle_flags(self, qtbot):
        bar = HardwareStatusBar()
        qtbot.addWidget(bar)
        bar.resize(800, 60)
        bar.push_throttle(0x000F)   # all four current-flag bits set
        bar.push_fan(7)
        bar.push_disk(50.0)
        bar.show()
        bar.repaint()

    def test_boot_only_throttle_flags(self, qtbot):
        bar = HardwareStatusBar()
        qtbot.addWidget(bar)
        bar.resize(800, 60)
        bar.push_throttle(0xF0000)  # only historical bits set
        bar.push_fan(3)
        bar.push_disk(50.0)
        bar.show()
        bar.repaint()

    def test_na_fan(self, qtbot):
        bar = HardwareStatusBar()
        qtbot.addWidget(bar)
        bar.resize(800, 60)
        bar.push_throttle(0)
        bar.push_fan(-1)
        bar.push_disk(50.0)
        bar.show()
        bar.repaint()

    def test_disk_at_zero(self, qtbot):
        bar = HardwareStatusBar()
        qtbot.addWidget(bar)
        bar.resize(800, 60)
        bar.push_throttle(0)
        bar.push_fan(2)
        bar.push_disk(0.0)
        bar.show()
        bar.repaint()

    def test_disk_at_100(self, qtbot):
        bar = HardwareStatusBar()
        qtbot.addWidget(bar)
        bar.resize(800, 60)
        bar.push_throttle(0)
        bar.push_fan(2)
        bar.push_disk(100.0)
        bar.show()
        bar.repaint()

    def test_disk_amber_threshold(self, qtbot):
        """75% disk should render in amber."""
        bar = HardwareStatusBar()
        qtbot.addWidget(bar)
        bar.resize(800, 60)
        bar.push_throttle(0)
        bar.push_fan(1)
        bar.push_disk(75.0)
        bar.show()
        bar.repaint()

    def test_disk_red_threshold(self, qtbot):
        """90% disk should render in red."""
        bar = HardwareStatusBar()
        qtbot.addWidget(bar)
        bar.resize(800, 60)
        bar.push_throttle(0)
        bar.push_fan(1)
        bar.push_disk(90.0)
        bar.show()
        bar.repaint()
