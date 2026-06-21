import psutil
from PyQt5.QtCore import QObject, QTimer, pyqtSignal


class DataSampler(QObject):
    cpu_sample  = pyqtSignal(float)
    temp_sample = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        psutil.cpu_percent(interval=None)  # warm up
        self.timer = QTimer()
        self.timer.timeout.connect(self._sample)

    def set_interval(self, ms):
        was_active = self.timer.isActive()
        self.timer.stop()
        self.timer.setInterval(ms)
        if was_active:
            self.timer.start()

    def start(self):
        self.timer.start()

    def _sample(self):
        cpu = psutil.cpu_percent(interval=None)
        temps = psutil.sensors_temperatures()
        try:
            temp = temps['cpu_thermal'][0].current
        except (KeyError, IndexError, TypeError):
            try:
                temp = int(open('/sys/class/thermal/thermal_zone0/temp').read()) / 1000.0
            except OSError:
                temp = 0.0
        self.cpu_sample.emit(cpu)
        self.temp_sample.emit(temp)
