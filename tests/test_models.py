"""
Unit tests for Transaction and TransactionEvent dataclasses.
No Qt or signals involved — pure Python dataclass behaviour.
"""
import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

import pytest

from core.models import Transaction, TransactionEvent


# ---------------------------------------------------------------------------
# TransactionEvent
# ---------------------------------------------------------------------------

class TestTransactionEvent:
    def test_fields_are_stored_correctly(self):
        ts = datetime(2024, 1, 15, 10, 30, 0)
        ev = TransactionEvent(
            timestamp=ts,
            source="MDB",
            direction="in",
            message="VEND REQUEST $2.50",
            raw="0x03 0x00 00fa",
        )
        assert ev.timestamp == ts
        assert ev.source == "MDB"
        assert ev.direction == "in"
        assert ev.message == "VEND REQUEST $2.50"
        assert ev.raw == "0x03 0x00 00fa"

    def test_raw_defaults_to_empty_string(self):
        ev = TransactionEvent(
            timestamp=datetime.now(),
            source="SYSTEM",
            direction="out",
            message="Payment flow started",
        )
        assert ev.raw == ""

    def test_source_values_are_plain_strings(self):
        for source in ("MDB", "SQUARE", "SYSTEM"):
            ev = TransactionEvent(datetime.now(), source, "in", "msg")
            assert ev.source == source

    def test_direction_values_are_plain_strings(self):
        for direction in ("in", "out"):
            ev = TransactionEvent(datetime.now(), "MDB", direction, "msg")
            assert ev.direction == direction


# ---------------------------------------------------------------------------
# Transaction — defaults
# ---------------------------------------------------------------------------

class TestTransactionDefaults:
    def test_status_defaults_to_pending(self):
        tx = Transaction(
            time=datetime.now(),
            item="Espresso",
            amount=2.50,
            payment_type="fiat",
        )
        assert tx.status == "pending"

    def test_events_list_defaults_to_empty(self):
        tx = Transaction(
            time=datetime.now(),
            item="Latte",
            amount=3.90,
            payment_type="fiat",
        )
        assert tx.events == []
        assert isinstance(tx.events, list)

    def test_tx_id_is_auto_generated(self):
        tx = Transaction(
            time=datetime.now(),
            item="Americano",
            amount=2.80,
            payment_type="fiat",
        )
        assert tx.tx_id is not None
        assert isinstance(tx.tx_id, str)
        assert len(tx.tx_id) > 0

    def test_tx_id_is_8_characters(self):
        """The factory slices uuid4 to 8 chars: str(uuid.uuid4())[:8]."""
        tx = Transaction(datetime.now(), "Cappuccino", 4.20, "fiat")
        assert len(tx.tx_id) == 8

    def test_explicit_fields_are_stored(self):
        ts = datetime(2024, 6, 1, 9, 0, 0)
        tx = Transaction(
            time=ts,
            item="Flat White",
            amount=4.50,
            payment_type="bitcoin",
            status="completed",
        )
        assert tx.time == ts
        assert tx.item == "Flat White"
        assert tx.amount == 4.50
        assert tx.payment_type == "bitcoin"
        assert tx.status == "completed"


# ---------------------------------------------------------------------------
# Transaction — tx_id uniqueness
# ---------------------------------------------------------------------------

class TestTransactionTxIdUniqueness:
    def test_two_instances_have_different_tx_ids(self):
        tx1 = Transaction(datetime.now(), "Item A", 1.00, "fiat")
        tx2 = Transaction(datetime.now(), "Item B", 2.00, "fiat")
        assert tx1.tx_id != tx2.tx_id

    def test_many_instances_have_unique_tx_ids(self):
        ids = [
            Transaction(datetime.now(), "Item", 1.00, "fiat").tx_id
            for _ in range(100)
        ]
        assert len(set(ids)) == 100, "Duplicate tx_id detected across 100 instances"

    def test_explicit_tx_id_overrides_default(self):
        tx = Transaction(
            time=datetime.now(),
            item="Mocha",
            amount=5.00,
            payment_type="fiat",
            tx_id="custom01",
        )
        assert tx.tx_id == "custom01"


# ---------------------------------------------------------------------------
# Transaction — events list independence
# ---------------------------------------------------------------------------

class TestTransactionEventsIsolation:
    def test_events_lists_are_independent_across_instances(self):
        """Each Transaction must get its own events list (default_factory)."""
        tx1 = Transaction(datetime.now(), "A", 1.0, "fiat")
        tx2 = Transaction(datetime.now(), "B", 2.0, "fiat")
        tx1.events.append(
            TransactionEvent(datetime.now(), "MDB", "in", "test event")
        )
        assert len(tx1.events) == 1
        assert len(tx2.events) == 0, (
            "tx2.events should be independent — shared list detected"
        )

    def test_status_values_are_accepted(self):
        for status in ("pending", "completed", "failed"):
            tx = Transaction(datetime.now(), "Item", 1.0, "fiat", status=status)
            assert tx.status == status

    def test_payment_type_values_are_accepted(self):
        for ptype in ("fiat", "bitcoin"):
            tx = Transaction(datetime.now(), "Item", 1.0, ptype)
            assert tx.payment_type == ptype
