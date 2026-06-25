import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock

import pytest
from core.bus import bus
from core.reporter import Reporter


class TestReporterFirestoreSignal:
    def test_heartbeat_emits_true_on_success(self, qtbot):
        reporter = Reporter()
        mock_ref = MagicMock()
        mock_ref.get.return_value.exists = True
        reporter._kiosk_ref = mock_ref

        received = []
        bus.firestore_ok_changed.connect(received.append)
        try:
            reporter._heartbeat()
            assert True in received
        finally:
            bus.firestore_ok_changed.disconnect(received.append)

    def test_heartbeat_emits_false_on_exception(self, qtbot):
        reporter = Reporter()
        mock_ref = MagicMock()
        mock_ref.get.side_effect = Exception("connection refused")
        reporter._kiosk_ref = mock_ref

        received = []
        bus.firestore_ok_changed.connect(received.append)
        try:
            reporter._heartbeat()
            assert False in received
        finally:
            bus.firestore_ok_changed.disconnect(received.append)

    def test_heartbeat_no_emit_when_kiosk_ref_is_none(self, qtbot):
        reporter = Reporter()
        reporter._kiosk_ref = None

        received = []
        bus.firestore_ok_changed.connect(received.append)
        try:
            reporter._heartbeat()
            assert received == []
        finally:
            bus.firestore_ok_changed.disconnect(received.append)
