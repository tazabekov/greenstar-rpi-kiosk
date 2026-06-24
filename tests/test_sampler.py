import os
import subprocess
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, mock_open, MagicMock
import pytest
from core.sampler import DataSampler


class TestNewSignalsEmitted:
    def test_fan_signal_emitted(self, qtbot):
        sampler = DataSampler()
        received = []
        sampler.fan_sample.connect(received.append)
        with patch.object(sampler, '_read_fan', return_value=3), \
             patch.object(sampler, '_read_disk', return_value=45.0), \
             patch.object(sampler, '_read_throttle', return_value=0), \
             patch('psutil.cpu_percent', return_value=10.0), \
             patch('psutil.sensors_temperatures',
                   return_value={'cpu_thermal': [MagicMock(current=55.0)]}):
            sampler._sample()
        assert received == [3]

    def test_disk_signal_emitted(self, qtbot):
        sampler = DataSampler()
        received = []
        sampler.disk_sample.connect(received.append)
        with patch.object(sampler, '_read_fan', return_value=-1), \
             patch.object(sampler, '_read_disk', return_value=72.5), \
             patch.object(sampler, '_read_throttle', return_value=0), \
             patch('psutil.cpu_percent', return_value=10.0), \
             patch('psutil.sensors_temperatures',
                   return_value={'cpu_thermal': [MagicMock(current=55.0)]}):
            sampler._sample()
        assert received == [pytest.approx(72.5)]

    def test_throttle_signal_emitted(self, qtbot):
        sampler = DataSampler()
        received = []
        sampler.throttle_sample.connect(received.append)
        with patch.object(sampler, '_read_fan', return_value=0), \
             patch.object(sampler, '_read_disk', return_value=50.0), \
             patch.object(sampler, '_read_throttle', return_value=0x50005), \
             patch('psutil.cpu_percent', return_value=10.0), \
             patch('psutil.sensors_temperatures',
                   return_value={'cpu_thermal': [MagicMock(current=55.0)]}):
            sampler._sample()
        assert received == [0x50005]


class TestReadFan:
    def test_returns_integer_from_sysfs(self):
        sampler = DataSampler()
        with patch('builtins.open', mock_open(read_data='4\n')):
            assert sampler._read_fan() == 4

    def test_strips_whitespace(self):
        sampler = DataSampler()
        with patch('builtins.open', mock_open(read_data='  2  \n')):
            assert sampler._read_fan() == 2

    def test_returns_minus_one_on_oserror(self):
        sampler = DataSampler()
        with patch('builtins.open', side_effect=OSError):
            assert sampler._read_fan() == -1

    def test_returns_minus_one_on_valueerror(self):
        sampler = DataSampler()
        with patch('builtins.open', mock_open(read_data='not-a-number\n')):
            assert sampler._read_fan() == -1


class TestReadDisk:
    def test_returns_usage_percent(self):
        sampler = DataSampler()
        mock_usage = MagicMock()
        mock_usage.percent = 38.2
        with patch('psutil.disk_usage', return_value=mock_usage):
            assert sampler._read_disk() == pytest.approx(38.2)

    def test_returns_zero_on_oserror(self):
        sampler = DataSampler()
        with patch('psutil.disk_usage', side_effect=OSError):
            assert sampler._read_disk() == 0.0


class TestReadThrottle:
    def test_parses_vcgencmd_output(self):
        sampler = DataSampler()
        mock_result = MagicMock()
        mock_result.stdout = b'throttled=0x50005\n'
        with patch('subprocess.run', return_value=mock_result):
            assert sampler._read_throttle() == 0x50005

    def test_parses_zero_ok_output(self):
        sampler = DataSampler()
        mock_result = MagicMock()
        mock_result.stdout = b'throttled=0x0\n'
        with patch('subprocess.run', return_value=mock_result):
            assert sampler._read_throttle() == 0

    def test_returns_zero_when_vcgencmd_missing(self):
        sampler = DataSampler()
        with patch('subprocess.run', side_effect=FileNotFoundError):
            assert sampler._read_throttle() == 0

    def test_returns_zero_on_timeout(self):
        sampler = DataSampler()
        with patch('subprocess.run',
                   side_effect=subprocess.TimeoutExpired('vcgencmd', 1)):
            assert sampler._read_throttle() == 0
