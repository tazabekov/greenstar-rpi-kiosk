import pytest
from unittest.mock import MagicMock, patch
from PyQt5.QtCore import QCoreApplication


@pytest.fixture(autouse=True)
def reset_bus():
    from core.bus import bus
    bus.crypto_mode = False
    bus.crypto_coin = ""
    yield
    bus.crypto_mode = False
    bus.crypto_coin = ""
    try:
        bus.payment_requested.disconnect()
    except TypeError:
        pass


def make_manager():
    import gc
    gc.collect()
    from core.crypto_session import CryptoSessionManager
    from core.bitpay import BitPayMockClient
    with patch("core.crypto_session.CryptoSessionManager._start_listener"):
        m = CryptoSessionManager(
            base_url="https://connect.squareup.com",
            headers_fn=lambda: {"Authorization": "Bearer test"},
            device_id="DEVICE123",
            kiosk_id="kiosk-001",
            bitpay_client=BitPayMockClient(),
        )
    return m


def test_waiting_for_vend_sets_bus_flags(qapp, qtbot):
    from core.bus import bus
    mgr = make_manager()
    session = {
        "session_id": "ses-1",
        "status": "waiting_for_vend",
        "coin": "ETH",
        "expires_at": None,
    }
    mgr._on_snapshot(session)
    assert bus.crypto_mode is True
    assert bus.crypto_coin == "ETH"


def test_waiting_for_vend_emits_signal(qapp, qtbot):
    from core.bus import bus
    mgr = make_manager()
    received = []
    bus.crypto_session_changed.connect(lambda s: received.append(s))
    session = {
        "session_id": "ses-1",
        "status": "waiting_for_vend",
        "coin": "BTC",
        "expires_at": None,
    }
    mgr._on_snapshot(session)
    assert len(received) == 1
    assert received[0]["coin"] == "BTC"


def test_stale_session_ignored(qapp, qtbot):
    from core.bus import bus
    mgr = make_manager()
    mgr._session_id = "active-session"
    session = {
        "session_id": "stale-session",
        "status": "waiting_for_vend",
        "coin": "SOL",
        "expires_at": None,
    }
    mgr._on_snapshot(session)
    assert bus.crypto_mode is False


def test_expired_status_clears_bus(qapp, qtbot):
    from core.bus import bus
    mgr = make_manager()
    bus.crypto_mode = True
    bus.crypto_coin = "BTC"
    mgr._session_id = "ses-1"
    mgr._on_snapshot({"session_id": "ses-1", "status": "expired", "coin": "BTC", "expires_at": None})
    assert bus.crypto_mode is False
    assert bus.crypto_coin == ""


def test_paid_status_clears_bus(qapp, qtbot):
    from core.bus import bus
    mgr = make_manager()
    bus.crypto_mode = True
    bus.crypto_coin = "LTC"
    mgr._session_id = "ses-1"
    mgr._on_snapshot({"session_id": "ses-1", "status": "paid", "coin": "LTC", "expires_at": None})
    assert bus.crypto_mode is False


def test_payment_requested_ignored_when_not_crypto(qapp, qtbot):
    from core.bus import bus
    mgr = make_manager()
    bus.crypto_mode = False
    with patch("core.crypto_session._CryptoQRWorker") as MockWorker:
        bus.payment_requested.emit("tx-1", 3.50, "fiat")
        MockWorker.assert_not_called()


def test_payment_requested_dispatches_worker_when_crypto_mode(qapp, qtbot):
    from core.bus import bus
    mgr = make_manager()
    bus.crypto_mode = True
    bus.crypto_coin = "BTC"
    mgr._session_id = "ses-1"
    with patch("core.crypto_session._CryptoQRWorker") as MockWorker:
        instance = MockWorker.return_value
        instance.qr_posted = MagicMock()
        instance.finished = MagicMock()
        instance.qr_posted.connect = MagicMock()
        instance.finished.connect = MagicMock()
        bus.payment_requested.emit("tx-1", 3.50, "fiat")
        MockWorker.assert_called_once()
        call_kwargs = MockWorker.call_args.kwargs
        assert call_kwargs["amount"] == 3.50
        assert call_kwargs["coin"] == "BTC"


def test_direct_bitcoin_creates_session(qapp, qtbot):
    from core.bus import bus
    mgr = make_manager()
    bus.crypto_mode = False
    with patch("core.crypto_session._CryptoQRWorker") as MockWorker:
        instance = MockWorker.return_value
        instance.qr_posted = MagicMock()
        instance.finished = MagicMock()
        instance.qr_posted.connect = MagicMock()
        instance.finished.connect = MagicMock()
        bus.payment_requested.emit("tx-1", 2.75, "bitcoin")
        assert bus.crypto_mode is True
        assert bus.crypto_coin == "BTC"
        MockWorker.assert_called_once()


def test_payment_requested_passes_bitpay_client_to_worker(qapp, qtbot):
    from core.bus import bus
    mgr = make_manager()
    bus.crypto_mode = True
    bus.crypto_coin = "BTC"
    mgr._session_id = "ses-1"
    with patch("core.crypto_session._CryptoQRWorker") as MockWorker:
        instance = MockWorker.return_value
        instance.qr_posted = MagicMock()
        instance.finished = MagicMock()
        instance.qr_posted.connect = MagicMock()
        instance.finished.connect = MagicMock()
        bus.payment_requested.emit("tx-1", 3.50, "fiat")
        call_kwargs = MockWorker.call_args.kwargs
        assert "bitpay_client" in call_kwargs
        assert "payment_link" not in call_kwargs


def test_poll_timer_starts_after_qr_posted(qapp, qtbot):
    from core.bus import bus
    mgr = make_manager()
    bus.crypto_mode = True
    mgr._session_id = "ses-1"
    mgr._on_qr_posted("action-abc", "mock-invoice-xyz")
    assert mgr._poll_timer.isActive()


def test_poll_timer_stops_after_clear_session(qapp, qtbot):
    from core.bus import bus
    mgr = make_manager()
    bus.crypto_mode = True
    mgr._session_id = "ses-1"
    mgr._on_qr_posted("action-abc", "mock-invoice-xyz")
    mgr._clear_session()
    assert not mgr._poll_timer.isActive()


def test_paid_status_writes_firestore_and_clears(qapp, qtbot):
    from core.bus import bus
    mgr = make_manager()
    bus.crypto_mode = True
    mgr._session_id = "ses-1"
    mgr._invoice_id = "mock-abc"
    with patch.object(mgr, "_write_firestore") as mock_write:
        mgr._on_payment_status("paid")
        mock_write.assert_called_once_with({"status": "paid"})
    assert bus.crypto_mode is False


def test_confirmed_status_also_triggers_paid(qapp, qtbot):
    from core.bus import bus
    mgr = make_manager()
    bus.crypto_mode = True
    mgr._session_id = "ses-1"
    mgr._invoice_id = "mock-abc"
    with patch.object(mgr, "_write_firestore") as mock_write:
        mgr._on_payment_status("confirmed")
        mock_write.assert_called_once_with({"status": "paid"})
    assert bus.crypto_mode is False


def test_new_status_does_not_clear(qapp, qtbot):
    from core.bus import bus
    mgr = make_manager()
    bus.crypto_mode = True
    mgr._session_id = "ses-1"
    mgr._invoice_id = "mock-abc"
    mgr._on_payment_status("new")
    assert bus.crypto_mode is True


def test_poll_timer_not_started_when_invoice_id_empty(qapp, qtbot):
    from core.bus import bus
    mgr = make_manager()
    bus.crypto_mode = True
    mgr._session_id = "ses-1"
    mgr._on_qr_posted("action-abc", "")  # empty invoice_id on worker failure
    assert not mgr._poll_timer.isActive()


def test_direct_bitcoin_includes_session_owner_and_processor(qapp, qtbot):
    from core.bus import bus
    mgr = make_manager()
    bus.crypto_mode = False
    written_data = {}
    with patch("core.crypto_session._CryptoQRWorker") as MockWorker:
        instance = MockWorker.return_value
        instance.qr_posted = MagicMock()
        instance.finished = MagicMock()
        instance.qr_posted.connect = MagicMock()
        instance.finished.connect = MagicMock()
        with patch.object(mgr, "_write_firestore", side_effect=lambda d: written_data.update(d)):
            bus.payment_requested.emit("tx-1", 2.75, "bitcoin")
    assert written_data.get("session_owner") == "kiosk"
    assert written_data.get("processor") == "bitpay"
