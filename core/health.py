from PyQt5.QtCore import QObject, pyqtSignal

_CPU_WARN  = 85.0
_TEMP_WARN = 70.0
_DISK_WARN = 75.0


class HealthMonitor(QObject):
    health_changed = pyqtSignal(str, str)  # color, reason

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cpu          = 0.0
        self._temp         = 0.0
        self._disk         = 0.0
        self._throttle     = 0
        self._camera_ok    = True
        self._firestore_ok = True
        self._mdb_ok       = True   # True by default; only False after a confirmed failure

    def on_cpu(self, value: float):
        self._cpu = value
        self._evaluate()

    def on_temp(self, value: float):
        self._temp = value
        self._evaluate()

    def on_disk(self, value: float):
        self._disk = value
        self._evaluate()

    def on_throttle(self, bitmask: int):
        self._throttle = bitmask
        self._evaluate()

    def on_camera_ok(self, ok: bool):
        self._camera_ok = ok
        self._evaluate()

    def on_firestore_ok(self, ok: bool):
        self._firestore_ok = ok
        self._evaluate()

    def on_mdb_ok(self, ok: bool):
        self._mdb_ok = ok
        self._evaluate()

    def _evaluate(self):
        if not self._mdb_ok:
            color, reason = "red", "MDB hat not responding"
        elif not self._firestore_ok:
            color, reason = "red", "Firestore write failed"
        elif not self._camera_ok:
            color, reason = "yellow", "Camera offline"
        elif self._throttle & 0xF:
            color, reason = "yellow", "CPU throttled"
        elif self._cpu >= _CPU_WARN:
            color, reason = "yellow", f"CPU {self._cpu:.0f}%"
        elif self._temp >= _TEMP_WARN:
            color, reason = "yellow", f"Temp {self._temp:.0f}°C"
        elif self._disk >= _DISK_WARN:
            color, reason = "yellow", f"Disk {self._disk:.0f}%"
        else:
            color, reason = "green", "All systems OK"
        self.health_changed.emit(color, reason)
