"""
PaymentModal logic tests.

We test the modal's internal state machine (_digits, _payment_type) and
signal emissions directly, avoiding any QPainter or display assertions.

Because PaymentModal.__init__ calls bus.payment_result.connect(), each
instance hooks into the singleton bus.  We use a fresh modal per test
and explicitly disconnect in teardown to avoid leakage.
"""
import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PyQt5.QtWidgets import QApplication

from ui.widgets.payment_modal import PaymentModal
from core.bus import bus


@pytest.fixture()
def modal(qtbot):
    """
    A PaymentModal with no parent (avoids resize-to-parent logic).
    Registered with qtbot so Qt cleans it up after the test.
    """
    m = PaymentModal(parent=None)
    qtbot.addWidget(m)
    yield m
    # Clean up any bus connections this instance added during _request()
    try:
        bus.payment_result.disconnect(m._on_result)
    except (RuntimeError, TypeError):
        pass


# ---------------------------------------------------------------------------
# Keypad digit input
# ---------------------------------------------------------------------------

class TestKeypadDigitInput:
    def test_single_digit_builds_amount_string(self, modal):
        modal._key_press("5")
        assert modal._digits == "5"

    def test_multiple_digits_concatenate(self, modal):
        for digit in ["1", "2", "3"]:
            modal._key_press(digit)
        assert modal._digits == "123"

    def test_digit_zero_is_appended(self, modal):
        modal._key_press("1")
        modal._key_press("0")
        assert modal._digits == "10"

    def test_amount_label_reflects_single_digit(self, modal):
        modal._key_press("7")
        assert modal._amount_label.text() == "7"

    def test_amount_label_reflects_multi_digit_integer(self, modal):
        for d in ["4", "2"]:
            modal._key_press(d)
        assert modal._amount_label.text() == "42"

    def test_all_digit_keys_are_accepted(self, modal):
        for digit in "9876543210":
            m = PaymentModal(parent=None)
            m._key_press(digit)
            assert m._digits == digit


# ---------------------------------------------------------------------------
# Backspace
# ---------------------------------------------------------------------------

class TestBackspace:
    def test_backspace_removes_last_digit(self, modal):
        modal._key_press("1")
        modal._key_press("2")
        modal._key_press("3")
        modal._key_press("⌫")
        assert modal._digits == "12"

    def test_backspace_on_empty_stays_empty(self, modal):
        modal._key_press("⌫")
        assert modal._digits == ""

    def test_backspace_after_single_digit_empties_string(self, modal):
        modal._key_press("9")
        modal._key_press("⌫")
        assert modal._digits == ""

    def test_backspace_removes_decimal_point(self, modal):
        modal._key_press("3")
        modal._key_press(".")
        modal._key_press("⌫")
        assert modal._digits == "3"
        assert "." not in modal._digits

    def test_multiple_backspaces_clear_to_empty(self, modal):
        for d in ["1", "2", "3"]:
            modal._key_press(d)
        for _ in range(5):  # more presses than digits
            modal._key_press("⌫")
        assert modal._digits == ""


# ---------------------------------------------------------------------------
# Decimal point
# ---------------------------------------------------------------------------

class TestDecimalPoint:
    def test_decimal_point_is_appended(self, modal):
        modal._key_press("3")
        modal._key_press(".")
        assert "." in modal._digits

    def test_only_one_decimal_point_allowed(self, modal):
        modal._key_press("1")
        modal._key_press(".")
        modal._key_press(".")  # second dot — should be ignored
        assert modal._digits.count(".") == 1

    def test_decimal_point_at_start_is_allowed(self, modal):
        modal._key_press(".")
        assert modal._digits == "."

    def test_two_decimal_digits_are_allowed(self, modal):
        modal._key_press("1")
        modal._key_press(".")
        modal._key_press("5")
        modal._key_press("0")
        assert modal._digits == "1.50"

    def test_third_decimal_digit_is_rejected(self, modal):
        modal._key_press("1")
        modal._key_press(".")
        modal._key_press("2")
        modal._key_press("5")
        modal._key_press("9")  # should be blocked — already 2 decimal places
        assert modal._digits == "1.25", (
            f"Expected '1.25' but got '{modal._digits}' — third decimal digit was accepted"
        )

    def test_amount_label_shows_decimal_in_progress(self, modal):
        modal._key_press("3")
        modal._key_press(".")
        modal._key_press("5")
        # Should display something with the decimal intact
        text = modal._amount_label.text()
        assert "." in text

    def test_integer_part_can_still_grow_after_decimal_starts(self, modal):
        """Digits before the '.' are not capped."""
        for d in ["1", "2", "3", "4"]:
            modal._key_press(d)
        modal._key_press(".")
        assert "1234." in modal._digits


# ---------------------------------------------------------------------------
# Amount validation — zero amount does not emit payment_requested
# ---------------------------------------------------------------------------

class TestAmountValidation:
    def test_zero_amount_does_not_emit_payment_requested(self, modal, qtbot):
        """With no digits entered (amount == 0), _request() must not fire the signal."""
        with qtbot.assertNotEmitted(bus.payment_requested, wait=200):
            modal._request()
        # Wait for the 600ms flash timer so it does not fire after modal teardown.
        qtbot.wait(700)

    def test_explicit_zero_does_not_emit_payment_requested(self, modal, qtbot):
        """Entering '0' and pressing Request must not emit."""
        modal._key_press("0")
        with qtbot.assertNotEmitted(bus.payment_requested, wait=200):
            modal._request()
        qtbot.wait(700)

    def test_only_decimal_point_does_not_emit(self, modal, qtbot):
        """'.' alone parses to 0 — should not emit."""
        modal._key_press(".")
        with qtbot.assertNotEmitted(bus.payment_requested, wait=200):
            modal._request()
        qtbot.wait(700)

    def test_valid_amount_does_emit_payment_requested(self, modal, qtbot):
        """Non-zero amount must emit payment_requested on the singleton bus."""
        modal._key_press("2")
        modal._key_press(".")
        modal._key_press("5")
        modal._key_press("0")

        with qtbot.waitSignal(bus.payment_requested, timeout=1000) as blocker:
            modal._request()

        tx_id, amount, ptype = blocker.args
        assert amount == pytest.approx(2.50)
        assert ptype == "fiat"  # default type
        assert tx_id  # non-empty

    def test_payment_requested_switches_stack_to_processing(self, modal, qtbot):
        """After a valid request, the stacked widget shows page 1 (processing)."""
        modal._key_press("1")
        modal._key_press("0")
        modal._key_press("0")

        with qtbot.waitSignal(bus.payment_requested, timeout=1000):
            modal._request()

        assert modal._stack.currentIndex() == 1

    def test_amount_label_flashes_red_on_zero(self, modal, qtbot):
        """When amount is 0, the label style changes to red to signal the error."""
        modal._request()  # amount is 0
        # Style should have changed immediately
        current_style = modal._amount_label.styleSheet()
        assert "#ff4444" in current_style, (
            "Amount label should turn red when amount is zero"
        )
        # Wait for the QTimer.singleShot(600ms) restore callback to fire
        # before the modal is destroyed, otherwise the next test's setup
        # receives a RuntimeError from the dangling lambda.
        qtbot.wait(700)


# ---------------------------------------------------------------------------
# Payment type toggle
# ---------------------------------------------------------------------------

class TestPaymentTypeToggle:
    def test_default_payment_type_is_fiat(self, modal):
        assert modal._payment_type == "fiat"

    def test_set_type_to_bitcoin(self, modal):
        modal._set_type("bitcoin")
        assert modal._payment_type == "bitcoin"

    def test_set_type_to_fiat_from_bitcoin(self, modal):
        modal._set_type("bitcoin")
        modal._set_type("fiat")
        assert modal._payment_type == "fiat"

    def test_toggle_between_types_multiple_times(self, modal):
        for expected in ["bitcoin", "fiat", "bitcoin", "fiat"]:
            modal._set_type(expected)
            assert modal._payment_type == expected

    def test_fiat_button_style_is_active_by_default(self, modal):
        """The fiat button should carry the BTN_TYPE_ACTIVE stylesheet initially."""
        from ui.widgets.payment_modal import BTN_TYPE_ACTIVE, BTN_TYPE_INACTIVE
        fiat_btn = modal._type_btns["fiat"]
        btc_btn  = modal._type_btns["bitcoin"]
        # Active button gets BTN_TYPE_ACTIVE, inactive gets BTN_TYPE_INACTIVE
        assert fiat_btn.styleSheet() == BTN_TYPE_ACTIVE
        assert btc_btn.styleSheet()  == BTN_TYPE_INACTIVE

    def test_bitcoin_button_becomes_active_after_set_type(self, modal):
        from ui.widgets.payment_modal import BTN_TYPE_ACTIVE, BTN_TYPE_INACTIVE
        modal._set_type("bitcoin")
        fiat_btn = modal._type_btns["fiat"]
        btc_btn  = modal._type_btns["bitcoin"]
        assert btc_btn.styleSheet()  == BTN_TYPE_ACTIVE
        assert fiat_btn.styleSheet() == BTN_TYPE_INACTIVE

    def test_payment_type_is_included_in_payment_requested(self, modal, qtbot):
        """The selected type must be forwarded with the payment_requested signal."""
        modal._key_press("5")
        modal._set_type("bitcoin")

        with qtbot.waitSignal(bus.payment_requested, timeout=1000) as blocker:
            modal._request()

        _, _, ptype = blocker.args
        assert ptype == "bitcoin"
