"""
SquareMockClient integration tests.

SquareMockClient hard-codes the module-level `bus` singleton from core.bus,
so we MUST use that same singleton here.  Each test fixture disconnects any
previously created mock client before wiring a fresh one, preventing signal
accumulation across tests.
"""
import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PyQt5.QtCore import QTimer

from core.bus import bus
from core.square import SquareMockClient


@pytest.fixture()
def mock_client(qtbot):
    """
    Create a fresh SquareMockClient connected to the singleton bus.

    After the test, disconnect the client so its slot cannot fire during
    subsequent tests.  We also disconnect by destroying the client object
    (Qt disconnects all signals when a QObject is deleted).
    """
    client = SquareMockClient()
    yield client
    # Explicit disconnect — guards against lingering QTimer callbacks too.
    try:
        bus.payment_requested.disconnect(client._handle)
    except (RuntimeError, TypeError):
        pass  # already disconnected or object deleted
    client.setParent(None)
    client.deleteLater()
    # Let the event loop process the deferred delete and any pending timers.
    qtbot.wait(100)


# ---------------------------------------------------------------------------
# Basic payment result
# ---------------------------------------------------------------------------

class TestSquareMockPaymentResult:
    def test_fiat_payment_emits_payment_result_within_10s(self, qtbot, mock_client):
        with qtbot.waitSignal(bus.payment_result, timeout=10_000) as blocker:
            bus.payment_requested.emit("tx-fiat-r01", 2.50, "fiat")

        tx_id, success, message = blocker.args
        assert tx_id == "tx-fiat-r01"

    def test_bitcoin_payment_emits_payment_result_within_10s(self, qtbot, mock_client):
        with qtbot.waitSignal(bus.payment_result, timeout=10_000) as blocker:
            bus.payment_requested.emit("tx-btc-r01", 2.50, "bitcoin")

        tx_id, success, message = blocker.args
        assert tx_id == "tx-btc-r01"

    def test_fiat_payment_result_has_success_true(self, qtbot, mock_client):
        with qtbot.waitSignal(bus.payment_result, timeout=10_000) as blocker:
            bus.payment_requested.emit("tx-fiat-ok01", 3.00, "fiat")

        _, success, _ = blocker.args
        assert success is True

    def test_bitcoin_payment_result_has_success_true(self, qtbot, mock_client):
        with qtbot.waitSignal(bus.payment_result, timeout=10_000) as blocker:
            bus.payment_requested.emit("tx-btc-ok01", 3.00, "bitcoin")

        _, success, _ = blocker.args
        assert success is True

    def test_fiat_result_message_contains_amount(self, qtbot, mock_client):
        with qtbot.waitSignal(bus.payment_result, timeout=10_000) as blocker:
            bus.payment_requested.emit("tx-fiat-msg01", 4.75, "fiat")

        _, _, message = blocker.args
        assert "4.75" in message

    def test_bitcoin_result_message_contains_bitcoin(self, qtbot, mock_client):
        with qtbot.waitSignal(bus.payment_result, timeout=10_000) as blocker:
            bus.payment_requested.emit("tx-btc-msg01", 2.00, "bitcoin")

        _, _, message = blocker.args
        assert "Bitcoin" in message

    def test_result_tx_id_matches_requested_tx_id(self, qtbot, mock_client):
        """Ensures the mock correctly routes results back to the right tx_id."""
        with qtbot.waitSignal(bus.payment_result, timeout=10_000) as blocker:
            bus.payment_requested.emit("unique-tx-abc", 1.00, "fiat")

        tx_id, _, _ = blocker.args
        assert tx_id == "unique-tx-abc"


# ---------------------------------------------------------------------------
# FIAT — transaction_event sequence
# ---------------------------------------------------------------------------

class TestFiatTransactionEvents:
    def test_fiat_emits_system_event_first(self, qtbot, mock_client):
        """The very first event must come from SYSTEM ('Payment flow started')."""
        events = []
        bus.transaction_event.connect(
            lambda tx_id, ev: events.append(ev) if tx_id == "tx-fiat-seq01" else None
        )

        # Wait for payment_result as the end marker.
        with qtbot.waitSignal(bus.payment_result, timeout=10_000):
            bus.payment_requested.emit("tx-fiat-seq01", 1.00, "fiat")

        sources = [ev.source for ev in events]
        assert sources[0] == "SYSTEM", f"Expected SYSTEM first, got: {sources}"

    def test_fiat_emits_square_events(self, qtbot, mock_client):
        """SQUARE events should appear during fiat flow."""
        events = []
        bus.transaction_event.connect(
            lambda tx_id, ev: events.append(ev) if tx_id == "tx-fiat-seq02" else None
        )

        with qtbot.waitSignal(bus.payment_result, timeout=10_000):
            bus.payment_requested.emit("tx-fiat-seq02", 1.00, "fiat")

        sources = [ev.source for ev in events]
        assert "SQUARE" in sources

    def test_fiat_emits_mdb_event(self, qtbot, mock_client):
        """MDB VEND APPROVED event must appear in the fiat flow."""
        events = []
        bus.transaction_event.connect(
            lambda tx_id, ev: events.append(ev) if tx_id == "tx-fiat-seq03" else None
        )

        with qtbot.waitSignal(bus.payment_result, timeout=10_000):
            bus.payment_requested.emit("tx-fiat-seq03", 1.00, "fiat")

        sources = [ev.source for ev in events]
        assert "MDB" in sources

    def test_fiat_mdb_event_contains_vend_approved(self, qtbot, mock_client):
        events = []
        bus.transaction_event.connect(
            lambda tx_id, ev: events.append(ev) if tx_id == "tx-fiat-seq04" else None
        )

        with qtbot.waitSignal(bus.payment_result, timeout=10_000):
            bus.payment_requested.emit("tx-fiat-seq04", 1.00, "fiat")

        mdb_events = [ev for ev in events if ev.source == "MDB"]
        assert any("VEND APPROVED" in ev.message for ev in mdb_events)

    def test_fiat_system_then_square_then_mdb_ordering(self, qtbot, mock_client):
        """The sources should appear in order: SYSTEM, then SQUARE(s), then MDB."""
        events = []
        bus.transaction_event.connect(
            lambda tx_id, ev: events.append(ev) if tx_id == "tx-fiat-ord01" else None
        )

        with qtbot.waitSignal(bus.payment_result, timeout=10_000):
            bus.payment_requested.emit("tx-fiat-ord01", 1.00, "fiat")

        sources = [ev.source for ev in events]
        # SYSTEM must come before any SQUARE, and SQUARE before MDB.
        first_system = next((i for i, s in enumerate(sources) if s == "SYSTEM"), None)
        first_square = next((i for i, s in enumerate(sources) if s == "SQUARE"), None)
        first_mdb    = next((i for i, s in enumerate(sources) if s == "MDB"),    None)
        assert first_system is not None
        assert first_square is not None
        assert first_mdb    is not None
        assert first_system < first_square, "SYSTEM should precede SQUARE"
        assert first_square < first_mdb,    "SQUARE should precede MDB"


# ---------------------------------------------------------------------------
# Bitcoin — transaction_event sequence
# ---------------------------------------------------------------------------

class TestBitcoinTransactionEvents:
    def test_bitcoin_emits_square_events(self, qtbot, mock_client):
        events = []
        bus.transaction_event.connect(
            lambda tx_id, ev: events.append(ev) if tx_id == "tx-btc-seq01" else None
        )

        with qtbot.waitSignal(bus.payment_result, timeout=10_000):
            bus.payment_requested.emit("tx-btc-seq01", 2.00, "bitcoin")

        sources = [ev.source for ev in events]
        assert "SQUARE" in sources

    def test_bitcoin_square_event_contains_bitcoin_in_message(self, qtbot, mock_client):
        """At least one SQUARE event message must mention Bitcoin or Crypto."""
        events = []
        bus.transaction_event.connect(
            lambda tx_id, ev: events.append(ev) if tx_id == "tx-btc-seq02" else None
        )

        with qtbot.waitSignal(bus.payment_result, timeout=10_000):
            bus.payment_requested.emit("tx-btc-seq02", 2.00, "bitcoin")

        square_events = [ev for ev in events if ev.source == "SQUARE"]
        assert any(
            "Bitcoin" in ev.message or "Crypto" in ev.message or "crypto" in ev.message
            for ev in square_events
        ), f"No Bitcoin/Crypto mention found in SQUARE messages: {[e.message for e in square_events]}"

    def test_bitcoin_emits_mdb_vend_approved(self, qtbot, mock_client):
        events = []
        bus.transaction_event.connect(
            lambda tx_id, ev: events.append(ev) if tx_id == "tx-btc-seq03" else None
        )

        with qtbot.waitSignal(bus.payment_result, timeout=10_000):
            bus.payment_requested.emit("tx-btc-seq03", 2.00, "bitcoin")

        mdb_events = [ev for ev in events if ev.source == "MDB"]
        assert any("VEND APPROVED" in ev.message for ev in mdb_events)

    def test_bitcoin_event_directions_are_valid(self, qtbot, mock_client):
        """All events should have direction 'in' or 'out'."""
        events = []
        bus.transaction_event.connect(
            lambda tx_id, ev: events.append(ev) if tx_id == "tx-btc-seq04" else None
        )

        with qtbot.waitSignal(bus.payment_result, timeout=10_000):
            bus.payment_requested.emit("tx-btc-seq04", 2.00, "bitcoin")

        for ev in events:
            assert ev.direction in ("in", "out"), (
                f"Unexpected direction '{ev.direction}' for event: {ev.message}"
            )
