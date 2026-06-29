# BitPay Integration — Kiosk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder payment link in `CryptoSessionManager` with a real `BitPayClient`/`BitPayMockClient` abstraction, and add invoice-status polling so `status: "paid"` is written to Firestore when the customer completes payment.

**Architecture:** A new `core/bitpay.py` module follows the same `make_X_client()` pattern as `core/square.py` — `BitPayMockClient` is returned when `BITPAY_API_KEY` is not set, `BitPayClient` (stubbed until credentials arrive) otherwise. `CryptoSessionManager` accepts a `bitpay_client` argument; `_CryptoQRWorker` calls `create_invoice()` to get the real payment URL before posting the Terminal QR action. After posting, a `QTimer` polls `get_invoice_status()` every 5 seconds on a daemon thread; when a paid status is detected it writes `status: "paid"` to Firestore and clears the session.

**Tech Stack:** Python 3, PyQt5 (QTimer, QThread, pyqtSignal), pytest + pytest-qt.

## Global Constraints

- Python 3, PyQt5 — no PyQt6 or PySide
- All Qt object interactions (signals, timers) must happen on the Qt main thread
- Blocking I/O (BitPay polling) runs in daemon threads; results bridge back via `pyqtSignal`
- `firebase_admin` is already initialised before `CryptoSessionManager` starts — reuse `firestore.client()` directly
- `PAID_STATUSES = frozenset({"paid", "confirmed", "complete"})` — exact set, defined in `core/bitpay.py`
- Mock client: `MOCK_PAID_AFTER_SECONDS = 10` (class-level constant, tests may override per instance)
- Poll interval: 5 000 ms (`_poll_timer.setInterval(5_000)`)
- `BitPayClient` methods raise `NotImplementedError` with the message `"BitPay API integration is pending credentials. See https://developer.bitpay.com/docs/getting-started"`
- Run tests with `python3 -m pytest tests/ -v` from `/home/ali/code/greenstar-rpi-kiosk`
- Commit and push after every task

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `core/bitpay.py` | **Create** | `BitPayMockClient`, `BitPayClient` stub, `PAID_STATUSES`, `make_bitpay_client()` |
| `tests/test_bitpay.py` | **Create** | Unit tests for both clients and factory |
| `.env.example` | **Modify** | Add `BITPAY_API_KEY=` entry |
| `core/crypto_session.py` | **Modify** | Inject `bitpay_client`; replace placeholder link; add poll timer, invoice ID, payment status signal and handler; add `session_owner`/`processor` to Path C |
| `tests/test_crypto_session.py` | **Modify** | Update `make_manager()` helper; add tests for polling and paid detection |
| `README.md` | **Modify** | Update Crypto Payment Mode section to reflect BitPay integration and polling |

---

### Task 1: `core/bitpay.py` — client abstraction and mock

**Files:**
- Create: `core/bitpay.py`
- Create: `tests/test_bitpay.py`
- Modify: `.env.example`

**Interfaces:**
- Produces:
  - `PAID_STATUSES: frozenset[str]` — `{"paid", "confirmed", "complete"}`
  - `BitPayMockClient.create_invoice(tx_id: str, amount_usd: float, coin: str) -> tuple[str, str]` — `(invoice_id, payment_url)`
  - `BitPayMockClient.get_invoice_status(invoice_id: str) -> str` — `"new"` or `"paid"` or `"invalid"`
  - `BitPayClient.create_invoice(...)` — raises `NotImplementedError`
  - `BitPayClient.get_invoice_status(...)` — raises `NotImplementedError`
  - `make_bitpay_client() -> BitPayMockClient | BitPayClient`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_bitpay.py
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python3 -m pytest tests/test_bitpay.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.bitpay'` or similar import errors for all tests.

- [ ] **Step 3: Create `core/bitpay.py`**

```python
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
```

- [ ] **Step 4: Add `BITPAY_API_KEY` to `.env.example`**

Open `.env.example` and append after the `GKM_ADMIN_PIN=` line:

```
# BitPay API key for crypto payment invoices.
# Get from: bitpay.com → Account → API Access Keys → Add New Token
# Leave blank to use BitPayMockClient (simulates paid after 10 s).
BITPAY_API_KEY=
```

- [ ] **Step 5: Run tests to confirm all pass**

```bash
python3 -m pytest tests/test_bitpay.py -v
```

Expected: 11 tests, all PASS.

- [ ] **Step 6: Run full suite to confirm no regressions**

```bash
python3 -m pytest tests/ -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add core/bitpay.py tests/test_bitpay.py .env.example
git commit -m "feat: add BitPayMockClient + BitPayClient stub with make_bitpay_client()"
git push
```

---

### Task 2: Wire BitPay into `CryptoSessionManager` — invoice creation, polling, paid detection

**Files:**
- Modify: `core/crypto_session.py`
- Modify: `tests/test_crypto_session.py`
- Modify: `README.md`

**Interfaces:**
- Consumes from Task 1:
  - `PAID_STATUSES` from `core.bitpay`
  - `BitPayMockClient` with `create_invoice(tx_id, amount_usd, coin) -> (invoice_id, payment_url)` and `get_invoice_status(invoice_id) -> str`
  - `make_bitpay_client()` from `core.bitpay`

- [ ] **Step 1: Write failing tests**

Add these tests to `tests/test_crypto_session.py`. First update the `make_manager()` helper (it currently calls `CryptoSessionManager` without a `bitpay_client` — Task 2 adds that parameter, so tests must pass the mock):

```python
# Replace the existing make_manager() helper at the top of test_crypto_session.py:

def make_manager():
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
```

Then add new tests at the bottom of the file:

```python
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
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
python3 -m pytest tests/test_crypto_session.py -v -k "bitpay_client or poll_timer or payment_status or session_owner"
```

Expected: all new tests FAIL (the parameter and methods don't exist yet).

- [ ] **Step 3: Rewrite `core/crypto_session.py`**

Replace the entire file with the following. Every change from the previous version is marked with a comment `# CHANGED` or `# NEW`:

```python
import os
import threading
import uuid
import logging
from datetime import datetime, timezone, timedelta

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal

from core.bus import bus

log = logging.getLogger(__name__)


class _CryptoQRWorker(QThread):
    """Posts a QR code display action to the Square Terminal using a BitPay invoice."""

    # CHANGED: was (action_id, payment_link) — now (action_id, invoice_id)
    qr_posted = pyqtSignal(str, str)  # action_id, invoice_id

    # CHANGED: accepts bitpay_client instead of payment_link
    def __init__(self, base_url, headers, device_id, kiosk_id, tx_id, amount, coin, bitpay_client, parent=None):
        super().__init__(parent)
        self._base_url      = base_url
        self._headers       = headers
        self._device_id     = device_id
        self._kiosk_id      = kiosk_id
        self._tx_id         = tx_id
        self._amount        = amount
        self._coin          = coin
        self._bitpay_client = bitpay_client  # CHANGED

    def run(self):
        # NEW step 1: Create BitPay invoice to get the real payment URL
        try:
            invoice_id, payment_url = self._bitpay_client.create_invoice(
                self._tx_id, self._amount, self._coin
            )
        except Exception as exc:
            log.error("_CryptoQRWorker: BitPay invoice creation failed: %s", exc)
            self.qr_posted.emit("", "")
            return

        # 2. Post Terminal QR action
        action_id = ""
        try:
            import requests
            body = {
                "idempotency_key": str(uuid.uuid4()),
                "action": {
                    "device_id": self._device_id,
                    "type": "QR_CODE",
                    "qr_code_options": {
                        "title": f"Pay with {self._coin}",
                        "body": f"Scan to pay ${self._amount:.2f} USD in {self._coin}",
                        "barcode_contents": payment_url,  # CHANGED: was placeholder
                    },
                },
            }
            resp = requests.post(
                f"{self._base_url}/v2/terminals/actions",
                json=body,
                headers=self._headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            action_id = data.get("action", {}).get("id", "")
        except Exception as exc:
            log.warning("_CryptoQRWorker: failed to post QR action: %s", exc)

        # 3. Write payment_shown to Firestore
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)
        try:
            from firebase_admin import firestore
            db = firestore.client()
            (
                db.collection("kiosks")
                  .document(self._kiosk_id)
                  .collection("crypto_sessions")
                  .document("active")
                  .update({
                      "status": "payment_shown",
                      "amount_usd": self._amount,
                      "payment_link": payment_url,  # CHANGED: was placeholder
                      "amount_crypto": None,
                      "expires_at": expires_at,
                  })
            )
        except Exception as exc:
            log.warning("_CryptoQRWorker: Firestore write error: %s", exc)

        # CHANGED: emit invoice_id (not payment_link) so manager can poll status
        self.qr_posted.emit(action_id, invoice_id)


class CryptoSessionManager(QObject):
    """
    Listens for crypto payment sessions written to Firestore by the kiosk-manager
    web app. When a session arrives, enters crypto mode and intercepts the next
    payment request to show a payment QR on the Square Terminal instead of a
    FIAT checkout. Polls BitPay invoice status to detect payment completion.
    """

    _snapshot_received       = pyqtSignal(object)   # session dict or None
    _qr_posted               = pyqtSignal(str, str)  # action_id, invoice_id
    _payment_status_received = pyqtSignal(str)       # NEW: poll result from daemon thread

    # CHANGED: added bitpay_client parameter
    def __init__(self, base_url, headers_fn, device_id, kiosk_id, bitpay_client, parent=None):
        super().__init__(parent)
        self._base_url      = base_url
        self._headers_fn    = headers_fn
        self._device_id     = device_id
        self._kiosk_id      = kiosk_id
        self._bitpay_client = bitpay_client  # NEW

        self._session_id = None
        self._action_id  = None
        self._invoice_id = None  # NEW

        self._expiry_timer = QTimer(self)
        self._expiry_timer.setSingleShot(True)
        self._expiry_timer.timeout.connect(self._on_expired)

        # NEW: poll timer — fires every 5 s after QR is posted
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(5_000)
        self._poll_timer.timeout.connect(self._poll_payment_status)

        self._snapshot_received.connect(self._on_snapshot)
        self._qr_posted.connect(self._on_qr_posted)
        self._payment_status_received.connect(self._on_payment_status)  # NEW
        bus.payment_requested.connect(self._on_payment_requested)

        self._start_listener()

    # ── Firestore listener ────────────────────────────────────────────────

    def _start_listener(self):
        t = threading.Thread(target=self._run_listener, daemon=True)
        t.start()

    def _run_listener(self):
        try:
            from firebase_admin import firestore
            db = firestore.client()
            doc_ref = (
                db.collection("kiosks")
                  .document(self._kiosk_id)
                  .collection("crypto_sessions")
                  .document("active")
            )
            self._watch = doc_ref.on_snapshot(self._firestore_callback)
            threading.Event().wait()
        except Exception as exc:
            log.warning("CryptoSessionManager: listener error: %s", exc)

    def _firestore_callback(self, doc_snapshots, changes, read_time):
        for snap in doc_snapshots:
            self._snapshot_received.emit(snap.to_dict() if snap.exists else None)

    # ── Session state machine (Qt main thread) ────────────────────────────

    def _on_snapshot(self, session):
        if not session:
            return

        sid    = session.get("session_id")
        status = session.get("status")

        if self._session_id and sid != self._session_id:
            return

        if status == "waiting_for_vend":
            self._session_id = sid
            bus.crypto_mode = True
            bus.crypto_coin = session.get("coin", "BTC")
            bus.crypto_session_changed.emit(session)
            self._restart_expiry_timer(session.get("expires_at"))

        elif status == "payment_shown":
            if not self._session_id:
                self._session_id = sid
            if not bus.crypto_mode:
                bus.crypto_mode = True
                bus.crypto_coin = session.get("coin", "BTC")
            self._restart_expiry_timer(session.get("expires_at"))
            bus.crypto_session_changed.emit(session)

        elif status in ("expired", "paid"):
            self._clear_session()

    def _restart_expiry_timer(self, expires_at):
        self._expiry_timer.stop()
        if not expires_at:
            return
        now = datetime.now(timezone.utc)
        try:
            deadline = expires_at.timestamp() if hasattr(expires_at, "timestamp") else float(expires_at)
            delta_ms = max(0, int((deadline - now.timestamp()) * 1000))
        except Exception:
            delta_ms = 60_000
        self._expiry_timer.start(delta_ms)

    def _clear_session(self):
        if not bus.crypto_mode and not self._session_id:
            return
        self._expiry_timer.stop()
        self._poll_timer.stop()    # NEW
        self._cancel_terminal_action()
        bus.crypto_mode = False
        bus.crypto_coin = ""
        self._session_id = None
        self._invoice_id = None    # NEW
        bus.crypto_session_changed.emit(None)

    # ── Expiry ────────────────────────────────────────────────────────────

    def _on_expired(self):
        log.info("CryptoSessionManager: session expired")
        self._clear_session()
        self._write_firestore({"status": "expired"})

    # ── Payment interception ──────────────────────────────────────────────

    def _on_payment_requested(self, tx_id, amount, payment_type):
        is_direct_bitcoin = (payment_type == "bitcoin" and not bus.crypto_mode)
        if not bus.crypto_mode and not is_direct_bitcoin:
            return

        if is_direct_bitcoin:
            new_sid = str(uuid.uuid4())
            self._session_id = new_sid
            bus.crypto_mode = True
            bus.crypto_coin = "BTC"
            initial_session = {
                "session_id":    new_sid,
                "session_owner": "kiosk",   # NEW: kiosk-initiated path
                "status":        "waiting_for_vend",
                "coin":          "BTC",
                "processor":     "bitpay",  # NEW
                "created_at":    datetime.now(timezone.utc),
                "expires_at":    None,
                "extended":      False,
                "amount_usd":    None,
                "amount_crypto": None,
                "payment_link":  None,
            }
            self._write_firestore(initial_session)
            bus.crypto_session_changed.emit(initial_session)

        worker = _CryptoQRWorker(
            base_url=self._base_url,
            headers=self._headers_fn(),
            device_id=self._device_id,
            kiosk_id=self._kiosk_id,
            tx_id=tx_id,
            amount=amount,
            coin=bus.crypto_coin,
            bitpay_client=self._bitpay_client,  # CHANGED: was payment_link=...
        )
        worker.qr_posted.connect(self._qr_posted)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    # CHANGED: now receives (action_id, invoice_id) not (action_id, payment_link)
    def _on_qr_posted(self, action_id, invoice_id):
        self._action_id  = action_id
        self._invoice_id = invoice_id   # NEW
        self._expiry_timer.stop()
        self._expiry_timer.start(60_000)
        if invoice_id:                  # NEW: only poll when we have a valid invoice
            self._poll_timer.start()

    # ── Payment status polling (NEW) ──────────────────────────────────────

    def _poll_payment_status(self):
        """Called by _poll_timer every 5 s — dispatches daemon thread for I/O."""
        if not self._invoice_id:
            return
        invoice_id = self._invoice_id
        t = threading.Thread(
            target=self._do_poll,
            args=(invoice_id,),
            daemon=True,
        )
        t.start()

    def _do_poll(self, invoice_id):
        """Runs on daemon thread — result bridges back via signal."""
        try:
            status = self._bitpay_client.get_invoice_status(invoice_id)
        except Exception as exc:
            log.warning("CryptoSessionManager: poll error: %s", exc)
            return
        self._payment_status_received.emit(status)

    def _on_payment_status(self, status):
        """Qt main thread — handles poll result."""
        from core.bitpay import PAID_STATUSES
        if status in PAID_STATUSES:
            log.info("CryptoSessionManager: payment confirmed (status=%s)", status)
            self._write_firestore({"status": "paid"})
            self._clear_session()

    # ── Terminal action cancel ────────────────────────────────────────────

    def _cancel_terminal_action(self):
        if not self._action_id:
            return
        action_id = self._action_id
        self._action_id = None
        t = threading.Thread(target=self._do_cancel, args=(action_id,), daemon=True)
        t.start()

    def _do_cancel(self, action_id):
        try:
            import requests
            requests.post(
                f"{self._base_url}/v2/terminals/actions/{action_id}/cancel",
                headers=self._headers_fn(),
                timeout=10,
            )
        except Exception:
            pass

    # ── Firestore write ───────────────────────────────────────────────────

    def _write_firestore(self, data):
        t = threading.Thread(target=self._do_write, args=(data,), daemon=True)
        t.start()

    def _do_write(self, data):
        try:
            from firebase_admin import firestore
            db = firestore.client()
            ref = (
                db.collection("kiosks")
                  .document(self._kiosk_id)
                  .collection("crypto_sessions")
                  .document("active")
            )
            if "session_id" in data:
                ref.set(data)
            else:
                ref.update(data)
        except Exception as exc:
            log.warning("CryptoSessionManager: Firestore write error: %s", exc)


def make_crypto_session_manager(parent=None):
    """
    Creates a CryptoSessionManager when all required env vars are set.
    Returns None and logs a warning otherwise (kiosk continues in FIAT-only mode).
    Auto-selects BitPayMockClient when BITPAY_API_KEY is not set.
    """
    from core.bitpay import make_bitpay_client  # NEW

    kiosk_id     = os.getenv("GKM_KIOSK_ID", "")
    access_token = os.getenv("SQUARE_ACCESS_TOKEN", "")
    device_id    = os.getenv("SQUARE_DEVICE_ID", "")
    sq_env       = os.getenv("SQUARE_ENVIRONMENT", "sandbox")
    base_url     = (
        "https://connect.squareup.com"
        if sq_env == "production"
        else "https://connect.squareupsandbox.com"
    )

    if not kiosk_id or not access_token:
        log.info("CryptoSessionManager: GKM_KIOSK_ID or SQUARE_ACCESS_TOKEN not set — disabled")
        return None

    def headers_fn():
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Square-Version": "2025-01-23",
        }

    bitpay_client = make_bitpay_client()  # NEW
    return CryptoSessionManager(base_url, headers_fn, device_id, kiosk_id, bitpay_client, parent)
```

- [ ] **Step 4: Run all tests to confirm they pass**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass. Specifically confirm:
- All 8 original `test_crypto_session.py` tests still pass
- All new `test_crypto_session.py` tests pass
- All `test_bitpay.py` tests still pass

- [ ] **Step 5: Update `README.md` — Crypto Payment Mode section**

Find the section starting with `### Crypto Payment Mode` (currently around line 254). Replace the entire section through the `### Bitcoin via Square Terminal` heading with:

```markdown
### Crypto Payment Mode (`core/crypto_session.py`, `core/bitpay.py`)

When crypto mode is active the kiosk bypasses Square FIAT checkout and posts a **`QR_CODE` Terminal Action** to the Square Terminal instead, showing a payment QR the customer scans with their phone.

**How it works:**

```
Customer phone
    │  scan static QR image on Square Terminal (uploaded via Square Dashboard)
    ▼
kiosk-manager web app  (/enable-crypto/[kiosk_id])
    │  write to Firestore: /kiosks/{id}/crypto_sessions/active
    ▼
CryptoSessionManager  (on_snapshot listener)
    │  sets bus.crypto_mode = True, bus.crypto_coin = "BTC"
    │  amber pill appears in kiosk header: ⟳ CRYPTO · BTC
    ▼
Payment trigger (MDB vend, manual modal, or direct Bitcoin selection)
    │  SquareClient skips — CryptoSessionManager intercepts
    ▼
_CryptoQRWorker  (QThread)
    │  BitPayClient.create_invoice() → (invoice_id, payment_url)
    │  POST /v2/terminals/actions  (type: QR_CODE, barcode_contents: payment_url)
    │  writes payment_shown to Firestore (amount_usd, payment_link, expires_at)
    ▼
Square Terminal shows payment QR for 60 s
    │  _poll_timer fires every 5 s → BitPayClient.get_invoice_status(invoice_id)
    ├── paid/confirmed/complete → writes status: "paid" to Firestore → session cleared
    └── expired → session cleared
```

**Three payment trigger paths:**
- **Path A** — MDB vend signal fires while `bus.crypto_mode == True`
- **Path B** — operator enters amount in payment modal while crypto mode active
- **Path C** — operator selects Bitcoin directly in payment modal (no prior web session); session written to Firestore with `session_owner: "kiosk"`

**Env vars:**
```
GKM_KIOSK_ID          must be set (also needed for Firestore in general)
SQUARE_ACCESS_TOKEN   must be set (same as FIAT mode)
SQUARE_DEVICE_ID      must be set
BITPAY_API_KEY        optional — leave blank to use BitPayMockClient (simulates paid after 10 s)
```

**BitPay client selection** (same pattern as Square):
- `BITPAY_API_KEY` set → `BitPayClient` (real API — credentials pending)
- `BITPAY_API_KEY` not set → `BitPayMockClient` (auto-reports paid after 10 s for dev/test)

**Terminal idle screen:** The static background image (showing the crypto invite QR code) is uploaded directly via the Square Dashboard — the kiosk app does not post any QR actions on startup or while idle.
```

- [ ] **Step 6: Run full test suite one final time**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add core/crypto_session.py tests/test_crypto_session.py README.md
git commit -m "feat: wire BitPay into CryptoSessionManager — real invoice link + paid polling"
git push
```
