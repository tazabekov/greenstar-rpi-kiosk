"""
AppBus signal tests.

Each test creates a *fresh* AppBus() instance — never the module-level
singleton — to prevent cross-test signal leakage.
"""
import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

import pytest
from PyQt5.QtCore import QObject, pyqtSignal

from core.bus import AppBus
from core.models import Transaction, TransactionEvent


# ---------------------------------------------------------------------------
# transaction_added signal
# ---------------------------------------------------------------------------

class TestTransactionAddedSignal:
    def test_fires_with_correct_transaction_object(self, qtbot):
        local_bus = AppBus()
        tx = Transaction(datetime.now(), "Espresso", 2.50, "fiat")

        received = []
        local_bus.transaction_added.connect(received.append)

        with qtbot.waitSignal(local_bus.transaction_added, timeout=1000) as blocker:
            local_bus.transaction_added.emit(tx)

        assert len(received) == 1
        assert received[0] is tx

    def test_carries_correct_tx_id(self, qtbot):
        local_bus = AppBus()
        tx = Transaction(datetime.now(), "Latte", 3.90, "bitcoin")

        with qtbot.waitSignal(local_bus.transaction_added, timeout=1000) as blocker:
            local_bus.transaction_added.emit(tx)

        emitted_tx = blocker.args[0]
        assert emitted_tx.tx_id == tx.tx_id

    def test_carries_correct_amount(self, qtbot):
        local_bus = AppBus()
        tx = Transaction(datetime.now(), "Flat White", 4.50, "fiat")

        with qtbot.waitSignal(local_bus.transaction_added, timeout=1000) as blocker:
            local_bus.transaction_added.emit(tx)

        assert blocker.args[0].amount == 4.50

    def test_carries_correct_payment_type(self, qtbot):
        local_bus = AppBus()
        tx = Transaction(datetime.now(), "Mocha", 5.00, "bitcoin")

        with qtbot.waitSignal(local_bus.transaction_added, timeout=1000) as blocker:
            local_bus.transaction_added.emit(tx)

        assert blocker.args[0].payment_type == "bitcoin"

    def test_multiple_emissions_received_in_order(self, qtbot):
        local_bus = AppBus()
        txs = [
            Transaction(datetime.now(), f"Item {i}", float(i), "fiat")
            for i in range(1, 4)
        ]
        received = []
        local_bus.transaction_added.connect(received.append)

        for tx in txs:
            local_bus.transaction_added.emit(tx)

        # Process pending events
        qtbot.wait(50)
        assert [r.item for r in received] == ["Item 1", "Item 2", "Item 3"]


# ---------------------------------------------------------------------------
# transaction_event signal
# ---------------------------------------------------------------------------

class TestTransactionEventSignal:
    def test_fires_with_correct_tx_id_and_event(self, qtbot):
        local_bus = AppBus()
        ev = TransactionEvent(datetime.now(), "SYSTEM", "out", "Payment flow started")

        with qtbot.waitSignal(local_bus.transaction_event, timeout=1000) as blocker:
            local_bus.transaction_event.emit("abc12345", ev)

        tx_id, received_ev = blocker.args
        assert tx_id == "abc12345"
        assert received_ev is ev

    def test_event_source_is_preserved(self, qtbot):
        local_bus = AppBus()
        ev = TransactionEvent(datetime.now(), "MDB", "in", "VEND REQUEST")

        with qtbot.waitSignal(local_bus.transaction_event, timeout=1000) as blocker:
            local_bus.transaction_event.emit("tx001", ev)

        _, received_ev = blocker.args
        assert received_ev.source == "MDB"

    def test_event_message_is_preserved(self, qtbot):
        local_bus = AppBus()
        ev = TransactionEvent(datetime.now(), "SQUARE", "out", "POST /v2/terminals/checkouts")

        with qtbot.waitSignal(local_bus.transaction_event, timeout=1000) as blocker:
            local_bus.transaction_event.emit("tx002", ev)

        _, received_ev = blocker.args
        assert received_ev.message == "POST /v2/terminals/checkouts"

    def test_signal_is_independent_per_bus_instance(self, qtbot):
        """Signals on one local bus do not bleed into another."""
        bus_a = AppBus()
        bus_b = AppBus()
        received_b = []
        bus_b.transaction_event.connect(lambda tx_id, ev: received_b.append(tx_id))

        ev = TransactionEvent(datetime.now(), "SYSTEM", "out", "msg")
        bus_a.transaction_event.emit("only-on-a", ev)
        qtbot.wait(50)

        assert received_b == [], "Signal from bus_a leaked into bus_b"


# ---------------------------------------------------------------------------
# payment_requested signal
# ---------------------------------------------------------------------------

class TestPaymentRequestedSignal:
    def test_fires_with_correct_tx_id_amount_type(self, qtbot):
        local_bus = AppBus()

        with qtbot.waitSignal(local_bus.payment_requested, timeout=1000) as blocker:
            local_bus.payment_requested.emit("tx-fiat-01", 3.75, "fiat")

        tx_id, amount, ptype = blocker.args
        assert tx_id == "tx-fiat-01"
        assert amount == pytest.approx(3.75)
        assert ptype == "fiat"

    def test_fires_for_bitcoin_payment_type(self, qtbot):
        local_bus = AppBus()

        with qtbot.waitSignal(local_bus.payment_requested, timeout=1000) as blocker:
            local_bus.payment_requested.emit("tx-btc-01", 2.00, "bitcoin")

        _, _, ptype = blocker.args
        assert ptype == "bitcoin"

    def test_amount_is_floating_point(self, qtbot):
        local_bus = AppBus()

        with qtbot.waitSignal(local_bus.payment_requested, timeout=1000) as blocker:
            local_bus.payment_requested.emit("tx-fp-01", 1.99, "fiat")

        _, amount, _ = blocker.args
        assert isinstance(amount, float)
        assert amount == pytest.approx(1.99)


# ---------------------------------------------------------------------------
# payment_result signal
# ---------------------------------------------------------------------------

class TestPaymentResultSignal:
    def test_fires_with_success_true_and_message(self, qtbot):
        local_bus = AppBus()

        with qtbot.waitSignal(local_bus.payment_result, timeout=1000) as blocker:
            local_bus.payment_result.emit("tx-ok-01", True, "$3.75 card payment completed")

        tx_id, success, message = blocker.args
        assert tx_id == "tx-ok-01"
        assert success is True
        assert message == "$3.75 card payment completed"

    def test_fires_with_success_false_and_message(self, qtbot):
        local_bus = AppBus()

        with qtbot.waitSignal(local_bus.payment_result, timeout=1000) as blocker:
            local_bus.payment_result.emit("tx-fail-01", False, "Payment canceled")

        tx_id, success, message = blocker.args
        assert tx_id == "tx-fail-01"
        assert success is False
        assert "canceled" in message.lower()

    def test_success_is_boolean(self, qtbot):
        local_bus = AppBus()

        with qtbot.waitSignal(local_bus.payment_result, timeout=1000) as blocker:
            local_bus.payment_result.emit("tx-bool-01", True, "ok")

        _, success, _ = blocker.args
        assert isinstance(success, bool)


# ---------------------------------------------------------------------------
# firestore_ok_changed signal
# ---------------------------------------------------------------------------

class TestFirestoreOkChangedSignal:
    def test_fires_true(self, qtbot):
        local_bus = AppBus()
        with qtbot.waitSignal(local_bus.firestore_ok_changed, timeout=1000) as blocker:
            local_bus.firestore_ok_changed.emit(True)
        assert blocker.args[0] is True

    def test_fires_false(self, qtbot):
        local_bus = AppBus()
        with qtbot.waitSignal(local_bus.firestore_ok_changed, timeout=1000) as blocker:
            local_bus.firestore_ok_changed.emit(False)
        assert blocker.args[0] is False


# ---------------------------------------------------------------------------
# camera_ok_changed signal
# ---------------------------------------------------------------------------

class TestCameraOkChangedSignal:
    def test_fires_true(self, qtbot):
        local_bus = AppBus()
        with qtbot.waitSignal(local_bus.camera_ok_changed, timeout=1000) as blocker:
            local_bus.camera_ok_changed.emit(True)
        assert blocker.args[0] is True

    def test_fires_false(self, qtbot):
        local_bus = AppBus()
        with qtbot.waitSignal(local_bus.camera_ok_changed, timeout=1000) as blocker:
            local_bus.camera_ok_changed.emit(False)
        assert blocker.args[0] is False
