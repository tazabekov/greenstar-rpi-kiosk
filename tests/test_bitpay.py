import pytest


def test_mock_create_invoice_returns_id_and_url():
    from core.bitpay import BitPayMockClient
    client = BitPayMockClient()
    invoice_id, url = client.create_invoice("tx-1", 3.50, "BTC")
    assert invoice_id.startswith("mock-")
    assert url == f"https://bitpay.com/invoice?id={invoice_id}"


def test_mock_invoice_status_new_immediately():
    from core.bitpay import BitPayMockClient
    client = BitPayMockClient()
    invoice_id, _ = client.create_invoice("tx-1", 3.50, "BTC")
    assert client.get_invoice_status(invoice_id) == "new"


def test_mock_invoice_status_paid_after_delay():
    from core.bitpay import BitPayMockClient
    client = BitPayMockClient()
    client.MOCK_PAID_AFTER_SECONDS = 0  # override to instant for test
    invoice_id, _ = client.create_invoice("tx-1", 3.50, "BTC")
    assert client.get_invoice_status(invoice_id) == "paid"


def test_mock_invoice_status_invalid_unknown_id():
    from core.bitpay import BitPayMockClient
    client = BitPayMockClient()
    assert client.get_invoice_status("no-such-id") == "invalid"


def test_mock_create_invoice_unique_ids():
    from core.bitpay import BitPayMockClient
    client = BitPayMockClient()
    id1, _ = client.create_invoice("tx-1", 1.00, "BTC")
    id2, _ = client.create_invoice("tx-2", 1.00, "BTC")
    assert id1 != id2


def test_real_client_create_raises():
    from core.bitpay import BitPayClient
    client = BitPayClient("dummy-key")
    with pytest.raises(NotImplementedError):
        client.create_invoice("tx-1", 1.00, "BTC")


def test_real_client_status_raises():
    from core.bitpay import BitPayClient
    client = BitPayClient("dummy-key")
    with pytest.raises(NotImplementedError):
        client.get_invoice_status("inv-1")


def test_make_bitpay_client_returns_mock_without_key(monkeypatch):
    monkeypatch.delenv("BITPAY_API_KEY", raising=False)
    import importlib
    import core.bitpay as bp
    importlib.reload(bp)
    from core.bitpay import make_bitpay_client, BitPayMockClient
    assert isinstance(make_bitpay_client(), BitPayMockClient)


def test_make_bitpay_client_returns_real_with_key(monkeypatch):
    monkeypatch.setenv("BITPAY_API_KEY", "test-key-abc")
    import importlib
    import core.bitpay as bp
    importlib.reload(bp)
    from core.bitpay import make_bitpay_client, BitPayClient
    assert isinstance(make_bitpay_client(), BitPayClient)


def test_paid_statuses_contains_expected_values():
    from core.bitpay import PAID_STATUSES
    assert "paid" in PAID_STATUSES
    assert "confirmed" in PAID_STATUSES
    assert "complete" in PAID_STATUSES
    assert "new" not in PAID_STATUSES
