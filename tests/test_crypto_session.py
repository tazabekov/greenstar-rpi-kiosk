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


def make_manager():
    from core.crypto_session import CryptoSessionManager
    with patch("core.crypto_session.CryptoSessionManager._start_listener"):
        m = CryptoSessionManager(
            base_url="https://connect.squareup.com",
            headers_fn=lambda: {"Authorization": "Bearer test"},
            device_id="DEVICE123",
            kiosk_id="kiosk-001",
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
