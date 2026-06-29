import os
import time
import uuid
import logging

log = logging.getLogger(__name__)

PAID_STATUSES = frozenset({"paid", "confirmed", "complete"})


class BitPayMockClient:
    """Dev/test mock — auto-selected when BITPAY_API_KEY is not set."""

    MOCK_PAID_AFTER_SECONDS = 10  # simulate customer paying after 10 s

    def __init__(self):
        self._invoices: dict = {}  # invoice_id → created_at (monotonic float)

    def create_invoice(self, tx_id: str, amount_usd: float, coin: str):
        """Returns (invoice_id, payment_url)."""
        invoice_id = f"mock-{uuid.uuid4().hex[:12]}"
        self._invoices[invoice_id] = time.monotonic()
        payment_url = f"https://bitpay.com/invoice?id={invoice_id}"
        log.info("BitPayMock: created invoice %s for $%.2f %s", invoice_id, amount_usd, coin)
        return invoice_id, payment_url

    def get_invoice_status(self, invoice_id: str) -> str:
        """Returns 'new', 'paid', or 'invalid'."""
        created = self._invoices.get(invoice_id)
        if created is None:
            return "invalid"
        if time.monotonic() - created >= self.MOCK_PAID_AFTER_SECONDS:
            return "paid"
        return "new"


class BitPayClient:
    """Production BitPay client — stub until API credentials arrive."""

    BASE_URL = "https://bitpay.com"

    def __init__(self, api_key: str):
        self._api_key = api_key

    def create_invoice(self, tx_id: str, amount_usd: float, coin: str):
        """Returns (invoice_id, payment_url). Raises NotImplementedError until wired."""
        raise NotImplementedError(
            "BitPay API integration is pending credentials. "
            "See https://developer.bitpay.com/docs/getting-started"
        )

    def get_invoice_status(self, invoice_id: str) -> str:
        """Returns status string. Raises NotImplementedError until wired."""
        raise NotImplementedError(
            "BitPay API integration is pending credentials. "
            "See https://developer.bitpay.com/docs/getting-started"
        )


def make_bitpay_client():
    """Returns BitPayClient when BITPAY_API_KEY is set, otherwise BitPayMockClient."""
    api_key = os.getenv("BITPAY_API_KEY", "")
    if api_key:
        log.info("BitPay: using BitPayClient")
        return BitPayClient(api_key)
    log.info("BitPay: BITPAY_API_KEY not set — using BitPayMockClient")
    return BitPayMockClient()
