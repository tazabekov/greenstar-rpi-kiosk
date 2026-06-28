# Crypto Payment Flow — Kiosk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `CryptoSessionManager` to the kiosk app that listens for customer-initiated crypto sessions via Firestore, intercepts payment requests when crypto mode is active, and posts a payment QR code to the Square Terminal.

**Architecture:** A new `core/crypto_session.py` module holds all crypto session logic. A Firestore `on_snapshot` listener runs in a daemon thread and posts events to the Qt main thread via an internal signal. A `_CryptoQRWorker(QThread)` handles the Square Terminal API call and Firestore write without blocking the UI. `SquareClient` returns early when `bus.crypto_mode` is `True`; `_IdleScreen` pauses when a session is active.

**Tech Stack:** PyQt5, firebase-admin (already installed), google-cloud-firestore on_snapshot, Square Terminal Actions API (`POST /v2/terminals/actions`), pytest-qt.

**Note:** This plan covers the kiosk (RPi) side only. The kiosk-manager web page (`/enable-crypto/[kiosk_id]`) is a separate plan in the kiosk-manager repo.

## Global Constraints

- Python 3, PyQt5 — no PyQt6 or PySide
- All Qt object interactions (signals, timers, widget updates) must happen on the Qt main thread
- Firestore `on_snapshot` callbacks arrive on a background thread — always bridge to Qt via `pyqtSignal`
- `firebase_admin` is already initialised by `Reporter` before `CryptoSessionManager` starts — reuse `firestore.client()` directly, do not call `initialize_app` again
- `GKM_KIOSK_ID` env var is the Firestore document key
- Square Terminal cancel endpoint is `POST /v2/terminals/actions/{id}/cancel` (not DELETE)
- Touch targets ≥ 44px; header pill must not break the 800×480 layout
- All tests use `pytest` + `pytest-qt`; run with `python3 -m pytest tests/ -v`
- Placeholder `payment_link`: `https://mygreenstar.org/pay/{tx_id}` — real processor is a future step

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `core/bus.py` | Modify | Add `crypto_session_changed` signal; add `__init__` with `crypto_mode`/`crypto_coin` attrs |
| `core/crypto_session.py` | Create | `CryptoSessionManager` + `_CryptoQRWorker` |
| `core/square.py` | Modify | Guard in `SquareClient._handle`; `_IdleScreen` pauses on crypto session |
| `ui/header.py` | Modify | Amber crypto-mode pill |
| `main.py` | Modify | Instantiate `CryptoSessionManager`; connect pill |
| `tests/test_crypto_session.py` | Create | Unit tests for session state machine |

---

### Task 1: Bus additions

**Files:**
- Modify: `core/bus.py`
- Test: `tests/test_bus.py`

**Interfaces:**
- Produces: `bus.crypto_session_changed` (`pyqtSignal(object)` — session dict or `None`), `bus.crypto_mode` (`bool`), `bus.crypto_coin` (`str`)

- [ ] **Step 1: Write failing test**

```python
# In tests/test_bus.py — add after existing tests

def test_crypto_session_changed_signal_exists(qapp):
    from core.bus import bus
    assert hasattr(bus, "crypto_session_changed")

def test_bus_crypto_mode_default(qapp):
    from core.bus import bus
    assert bus.crypto_mode is False
    assert bus.crypto_coin == ""

def test_crypto_session_changed_emits_dict(qapp, qtbot):
    from core.bus import bus
    received = []
    bus.crypto_session_changed.connect(lambda s: received.append(s))
    bus.crypto_session_changed.emit({"status": "waiting_for_vend", "coin": "BTC"})
    assert received[0]["coin"] == "BTC"

def test_crypto_session_changed_emits_none(qapp, qtbot):
    from core.bus import bus
    received = []
    bus.crypto_session_changed.connect(lambda s: received.append(s))
    bus.crypto_session_changed.emit(None)
    assert received[0] is None
```

- [ ] **Step 2: Run to confirm failure**

```bash
python3 -m pytest tests/test_bus.py::test_crypto_session_changed_signal_exists tests/test_bus.py::test_bus_crypto_mode_default -v
```

Expected: `AttributeError` or `FAILED`.

- [ ] **Step 3: Implement**

```python
# core/bus.py — full file replacement
from PyQt5.QtCore import QObject, pyqtSignal


class AppBus(QObject):
    transaction_added          = pyqtSignal(object)           # Transaction
    transaction_event          = pyqtSignal(str, object)      # tx_id, TransactionEvent
    payment_requested          = pyqtSignal(str, float, str)  # tx_id, amount, payment_type
    payment_cancel_requested   = pyqtSignal(str)              # tx_id
    payment_result             = pyqtSignal(str, bool, str)   # tx_id, success, message
    settings_changed           = pyqtSignal(str, str, str)    # name, location, kiosk_id
    snapshot_interval_changed  = pyqtSignal(int)              # minutes; 0 = disabled
    firestore_ok_changed       = pyqtSignal(bool)
    camera_ok_changed          = pyqtSignal(bool)
    crypto_session_changed     = pyqtSignal(object)           # session dict or None

    def __init__(self):
        super().__init__()
        self.crypto_mode = False   # True while a crypto session is active
        self.crypto_coin = ""      # "BTC" | "ETH" | "SOL" | "LTC"


bus = AppBus()
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_bus.py -v
```

Expected: all bus tests pass.

- [ ] **Step 5: Commit**

```bash
git add core/bus.py tests/test_bus.py
git commit -m "feat: add crypto_session_changed signal and crypto_mode attrs to AppBus"
```

---

### Task 2: CryptoSessionManager — Firestore listener + session activation

**Files:**
- Create: `core/crypto_session.py`
- Create: `tests/test_crypto_session.py`

**Interfaces:**
- Consumes: `bus.crypto_session_changed`, `bus.crypto_mode`, `bus.crypto_coin` (from Task 1)
- Produces: `CryptoSessionManager(base_url, headers_fn, device_id, kiosk_id, parent=None)`; sets `bus.crypto_mode`, `bus.crypto_coin`, emits `bus.crypto_session_changed`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_crypto_session.py
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
python3 -m pytest tests/test_crypto_session.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.crypto_session'`

- [ ] **Step 3: Implement skeleton + listener + session activation**

```python
# core/crypto_session.py
import os
import threading
import uuid
import logging
from datetime import datetime, timezone, timedelta

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from core.bus import bus

log = logging.getLogger(__name__)


class CryptoSessionManager(QObject):
    """
    Listens for crypto payment sessions written to Firestore by the kiosk-manager
    web app. When a session arrives, enters crypto mode and intercepts the next
    payment request to show a payment QR on the Square Terminal instead of a
    FIAT checkout.
    """

    # Internal bridge: Firestore thread → Qt main thread
    _snapshot_received = pyqtSignal(object)   # session dict or None
    _qr_posted         = pyqtSignal(str, str) # action_id, payment_link

    def __init__(self, base_url, headers_fn, device_id, kiosk_id, parent=None):
        super().__init__(parent)
        self._base_url   = base_url
        self._headers_fn = headers_fn
        self._device_id  = device_id
        self._kiosk_id   = kiosk_id

        self._session_id = None  # guards against stale Firestore docs
        self._action_id  = None  # active Terminal QR action ID

        self._expiry_timer = QTimer(self)
        self._expiry_timer.setSingleShot(True)
        self._expiry_timer.timeout.connect(self._on_expired)

        self._snapshot_received.connect(self._on_snapshot)
        self._qr_posted.connect(self._on_qr_posted)
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
            threading.Event().wait()  # block forever — daemon dies with process
        except Exception as exc:
            log.warning("CryptoSessionManager: listener error: %s", exc)

    def _firestore_callback(self, doc_snapshots, changes, read_time):
        """Called on Firestore background thread — bridge to Qt via signal."""
        for snap in doc_snapshots:
            self._snapshot_received.emit(snap.to_dict() if snap.exists else None)

    # ── Session state machine (Qt main thread) ────────────────────────────

    def _on_snapshot(self, session):
        if not session:
            return

        sid    = session.get("session_id")
        status = session.get("status")

        # Reject snapshots from a different session than the one we're tracking
        if self._session_id and sid != self._session_id:
            return

        if status == "waiting_for_vend":
            self._session_id = sid
            bus.crypto_mode = True
            bus.crypto_coin = session.get("coin", "BTC")
            bus.crypto_session_changed.emit(session)
            self._restart_expiry_timer(session.get("expires_at"))

        elif status == "payment_shown":
            # expires_at may have been extended — restart timer
            self._restart_expiry_timer(session.get("expires_at"))
            bus.crypto_session_changed.emit(session)

        elif status in ("expired", "paid"):
            self._clear_session()

    def _restart_expiry_timer(self, expires_at):
        self._expiry_timer.stop()
        if not expires_at:
            return
        now = datetime.now(timezone.utc)
        # Firestore timestamps have a .timestamp() method
        try:
            deadline = expires_at.timestamp() if hasattr(expires_at, "timestamp") else float(expires_at)
            delta_ms = max(0, int((deadline - now.timestamp()) * 1000))
        except Exception:
            delta_ms = 60_000
        self._expiry_timer.start(delta_ms)

    def _clear_session(self):
        self._expiry_timer.stop()
        self._cancel_terminal_action()
        bus.crypto_mode = False
        bus.crypto_coin = ""
        self._session_id = None
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

        # Path C: direct bitcoin with no active web session
        if is_direct_bitcoin:
            new_sid = str(uuid.uuid4())
            self._session_id = new_sid
            bus.crypto_mode = True
            bus.crypto_coin = "BTC"
            initial_session = {
                "session_id": new_sid,
                "status": "waiting_for_vend",
                "coin": "BTC",
                "created_at": datetime.now(timezone.utc),
                "expires_at": None,
                "extended": False,
                "amount_usd": None,
                "amount_crypto": None,
                "payment_link": None,
            }
            self._write_firestore(initial_session)
            bus.crypto_session_changed.emit(initial_session)

        # Placeholder payment link — replaced by real processor in next step
        payment_link = f"https://mygreenstar.org/pay/{tx_id}"

        worker = _CryptoQRWorker(
            base_url=self._base_url,
            headers=self._headers_fn(),
            device_id=self._device_id,
            kiosk_id=self._kiosk_id,
            tx_id=tx_id,
            amount=amount,
            coin=bus.crypto_coin,
            payment_link=payment_link,
        )
        worker.qr_posted.connect(self._qr_posted)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_qr_posted(self, action_id, payment_link):
        self._action_id = action_id
        self._expiry_timer.stop()
        self._expiry_timer.start(60_000)  # 1-minute payment window

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
                ref.set(data)   # full write for new sessions
            else:
                ref.update(data)  # partial update for status changes
        except Exception as exc:
            log.warning("CryptoSessionManager: Firestore write error: %s", exc)
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_crypto_session.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add core/crypto_session.py tests/test_crypto_session.py
git commit -m "feat: add CryptoSessionManager with Firestore listener and session activation"
```

---

### Task 3: `_CryptoQRWorker` — Terminal QR posting + Firestore payment_shown write

**Files:**
- Modify: `core/crypto_session.py` (append class)
- Modify: `tests/test_crypto_session.py` (append tests)

**Interfaces:**
- Consumes: `CryptoSessionManager._on_payment_requested` (from Task 2)
- Produces: `_CryptoQRWorker(QThread)` with `qr_posted = pyqtSignal(str, str)` (action_id, payment_link)

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_crypto_session.py

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
```

- [ ] **Step 2: Run to confirm failure**

```bash
python3 -m pytest tests/test_crypto_session.py::test_payment_requested_ignored_when_not_crypto tests/test_crypto_session.py::test_payment_requested_dispatches_worker_when_crypto_mode -v
```

Expected: `FAILED` — `_CryptoQRWorker` not defined.

- [ ] **Step 3: Implement `_CryptoQRWorker`** — append to `core/crypto_session.py`

```python
# Append to core/crypto_session.py

from PyQt5.QtCore import QThread


class _CryptoQRWorker(QThread):
    """Posts a QR_CODE Terminal action and writes payment_shown to Firestore."""

    qr_posted = pyqtSignal(str, str)  # action_id, payment_link

    def __init__(self, base_url, headers, device_id, kiosk_id,
                 tx_id, amount, coin, payment_link, parent=None):
        super().__init__(parent)
        self._base_url    = base_url
        self._headers     = headers
        self._device_id   = device_id
        self._kiosk_id    = kiosk_id
        self._tx_id       = tx_id
        self._amount      = amount
        self._coin        = coin
        self._payment_link = payment_link

    def run(self):
        import uuid as uuid_mod
        try:
            import requests
        except ImportError:
            log.error("_CryptoQRWorker: requests not installed")
            return

        # 1. Post Terminal QR action
        body = {
            "idempotency_key": str(uuid_mod.uuid4()),
            "action": {
                "device_id": self._device_id,
                "type": "QR_CODE",
                "qr_code_options": {
                    "title": f"Pay with {self._coin}",
                    "body": f"Scan to pay ${self._amount:.2f}",
                    "barcode_contents": self._payment_link,
                },
            },
        }
        try:
            r = requests.post(
                f"{self._base_url}/v2/terminals/actions",
                headers=self._headers,
                json=body,
                timeout=10,
            )
            r.raise_for_status()
            action_id = r.json().get("action", {}).get("id", "")
        except Exception as exc:
            log.error("_CryptoQRWorker: Terminal API error: %s", exc)
            action_id = ""

        # 2. Write payment_shown to Firestore
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
                      "payment_link": self._payment_link,
                      "amount_crypto": None,  # future: from payment processor
                      "expires_at": expires_at,
                  })
            )
        except Exception as exc:
            log.warning("_CryptoQRWorker: Firestore write error: %s", exc)

        self.qr_posted.emit(action_id, self._payment_link)
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_crypto_session.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add core/crypto_session.py tests/test_crypto_session.py
git commit -m "feat: add _CryptoQRWorker — posts Terminal QR action and writes payment_shown to Firestore"
```

---

### Task 4: SquareClient guard + `_IdleScreen` crypto pause

**Files:**
- Modify: `core/square.py`
- Modify: `tests/test_square_mock.py` (append)

**Interfaces:**
- Consumes: `bus.crypto_mode` (Task 1), `bus.crypto_session_changed` (Task 1)

- [ ] **Step 1: Write failing tests**

```python
# Append to tests/test_square_mock.py

def test_square_client_skips_when_crypto_mode(qapp, qtbot):
    """SquareClient._handle must return early when bus.crypto_mode is True."""
    from core.bus import bus
    from core.square import SquareClient
    from unittest.mock import patch

    bus.crypto_mode = True
    try:
        client = SquareClient()
        with patch.object(client, '_workers', {}):
            with patch('core.square._PaymentWorker') as MockWorker:
                bus.payment_requested.emit("tx-skip", 1.00, "fiat")
                MockWorker.assert_not_called()
    finally:
        bus.crypto_mode = False
```

- [ ] **Step 2: Run to confirm failure**

```bash
python3 -m pytest tests/test_square_mock.py::test_square_client_skips_when_crypto_mode -v
```

Expected: `FAILED` — worker is called even when `crypto_mode=True`.

- [ ] **Step 3: Add guard to `SquareClient._handle`**

In `core/square.py`, locate `SquareClient._handle` and add one guard at the top:

```python
def _handle(self, tx_id, amount, payment_type):
    if bus.crypto_mode:
        return  # CryptoSessionManager handles this payment
    w = _PaymentWorker(
        tx_id, amount, payment_type,
        self._base_url, self._headers(), self._device, self._location,
    )
    self._workers[tx_id] = w
    w.event_ready.connect(bus.transaction_event)
    w.done.connect(bus.payment_result)
    w.finished.connect(lambda worker=w: self._workers.pop(worker._tx_id, None))
    w.start()
```

- [ ] **Step 4: Wire `_IdleScreen` to crypto session signal**

In `core/square.py`, in `_IdleScreen.__init__`, add after the existing bus connections:

```python
bus.crypto_session_changed.connect(self._on_crypto_session)
```

Add the slot at the end of `_IdleScreen`:

```python
def _on_crypto_session(self, session):
    if session is None:
        # Session cleared — restore idle screen (same as payment done)
        self._active = True
        QTimer.singleShot(3000, self._show)
    else:
        # Session active — suppress idle screen
        self._active = False
        self._cancel_current()
```

- [ ] **Step 5: Run all tests**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass including the new guard test.

- [ ] **Step 6: Commit**

```bash
git add core/square.py tests/test_square_mock.py
git commit -m "feat: guard SquareClient against crypto mode; pause IdleScreen during crypto sessions"
```

---

### Task 5: UI indicator — crypto mode pill in header

**Files:**
- Modify: `ui/header.py`
- Modify: `main.py` (connect signal)

**Interfaces:**
- Consumes: `bus.crypto_session_changed` (Task 1)
- Produces: `HeaderWidget.update_crypto_session(session)` slot

- [ ] **Step 1: Add `update_crypto_session` slot to `HeaderWidget`**

In `ui/header.py`, import `QLabel` (already imported). Add the `_crypto_pill` widget in `HeaderWidget.__init__` immediately before `layout.addStretch()`. Insert just after the `layout.addWidget(logo)` line:

```python
# Crypto mode indicator pill — hidden by default
self._crypto_pill = QLabel()
self._crypto_pill.setFixedHeight(28)
self._crypto_pill.setAlignment(Qt.AlignCenter)
self._crypto_pill.setStyleSheet(
    "QLabel { background: #b45309; color: #fff8e7; border-radius: 6px;"
    " padding: 0 10px; font-size: 11pt; font-weight: bold; border: none; }"
)
self._crypto_pill.hide()
layout.addWidget(self._crypto_pill)
```

Then add the slot at the end of `HeaderWidget`:

```python
@pyqtSlot(object)
def update_crypto_session(self, session):
    if session is None:
        self._crypto_pill.hide()
        return
    status = session.get("status", "")
    coin   = session.get("coin", "CRYPTO")
    if status == "waiting_for_vend":
        self._crypto_pill.setText(f"⟳ CRYPTO · {coin}")
    elif status == "payment_shown":
        self._crypto_pill.setText(f"⏳ {coin} PAYMENT")
    else:
        self._crypto_pill.hide()
        return
    self._crypto_pill.show()
```

- [ ] **Step 2: Connect in `main.py`**

In `main.py`, after the `self._square = make_square_client(self)` line, add:

```python
bus.crypto_session_changed.connect(self._header.update_crypto_session)
```

- [ ] **Step 3: Visual test — restart the app and verify**

```bash
# Kill running kiosk and restart
pkill -f "python3.*main.py"; sleep 1
DISPLAY=:0 nohup python3 /home/ali/code/greenstar-rpi-kiosk/main.py > /tmp/kiosk.log 2>&1 &
```

Trigger a crypto session by emitting the signal from a Python REPL:

```python
# Run in a separate terminal:
python3 -c "
from PyQt5.QtWidgets import QApplication
import sys
app = QApplication.instance() or QApplication(sys.argv)
from core.bus import bus
bus.crypto_session_changed.emit({'status': 'waiting_for_vend', 'coin': 'BTC'})
"
```

Expected: amber pill appears in header showing `⟳ CRYPTO · BTC`.

Emit `None` to verify it disappears:
```python
bus.crypto_session_changed.emit(None)
```

- [ ] **Step 4: Run test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests still pass (no regressions — pill is a pure UI addition).

- [ ] **Step 5: Commit**

```bash
git add ui/header.py main.py
git commit -m "feat: add crypto mode pill to header, connected to bus.crypto_session_changed"
```

---

### Task 6: Wire `CryptoSessionManager` into `main.py`

**Files:**
- Modify: `main.py`

**Interfaces:**
- Consumes: `CryptoSessionManager` (Task 2), `make_square_client` return value (for base_url/headers/device_id)
- Produces: fully wired crypto session flow end-to-end

- [ ] **Step 1: Add factory function to `core/crypto_session.py`**

Append to `core/crypto_session.py`:

```python
def make_crypto_session_manager(parent=None):
    """
    Creates a CryptoSessionManager when all required env vars are set.
    Returns None and logs a warning otherwise (kiosk continues in FIAT-only mode).
    """
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

    return CryptoSessionManager(base_url, headers_fn, device_id, kiosk_id, parent)
```

- [ ] **Step 2: Import and instantiate in `main.py`**

Add to imports at the top of `main.py`:

```python
from core.crypto_session import make_crypto_session_manager
```

In `MainWindow.__init__`, after `self._square = make_square_client(self)`, add:

```python
self._crypto = make_crypto_session_manager(self)
```

- [ ] **Step 3: Connect crypto pill (if not already done in Task 5)**

Verify this line is present after the `make_crypto_session_manager` call:

```python
bus.crypto_session_changed.connect(self._header.update_crypto_session)
```

- [ ] **Step 4: Run full test suite**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: End-to-end smoke test**

Restart the app and open the Square Terminal. Trigger a BTC payment from the payment modal (tap ₿ Bitcoin, enter an amount, tap Request Payment).

Expected:
- Amber pill appears in kiosk header: `⏳ BTC PAYMENT`
- Square Terminal shows a QR code with title "Pay with BTC"
- After 60 seconds the QR disappears and pill clears (expiry)

Check logs:

```bash
tail -f /tmp/kiosk.log | grep -i crypto
```

- [ ] **Step 6: Commit**

```bash
git add core/crypto_session.py main.py
git commit -m "feat: wire CryptoSessionManager into main.py via make_crypto_session_manager"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Firestore `on_snapshot` listener on `/kiosks/{kiosk_id}/crypto_sessions/active` | Task 2 |
| `waiting_for_vend` → set `bus.crypto_mode`, `bus.crypto_coin`, emit signal | Task 2 |
| `expired`/`paid` → clear bus flags, emit `None` | Task 2 |
| Stale session guard via `session_id` | Task 2 |
| Path A/B (crypto mode active) interception | Task 3 |
| Path C (direct bitcoin, no session) creates Firestore doc | Task 3 |
| Post `QR_CODE` Terminal action | Task 3 |
| Write `payment_shown` to Firestore with `amount_usd`, `payment_link`, `expires_at` | Task 3 |
| `expires_at` timer — restart on Firestore update (extension) | Task 2 `_on_snapshot` → `_restart_expiry_timer` |
| Expiry: cancel Terminal action, write `expired`, clear bus | Task 2 `_on_expired` + `_clear_session` |
| `SquareClient._handle` returns early when `bus.crypto_mode` | Task 4 |
| `_IdleScreen` pauses during crypto session | Task 4 |
| UI indicator pill in header (waiting / payment_shown / cleared) | Task 5 |
| Wired in `main.py` | Task 6 |
| `paid` status clears session | Task 2 `_on_snapshot` |
| `amount_crypto` is `None` (placeholder, processor is future step) | Task 3 |

**No gaps found.**

**Placeholder scan:** No TBD/TODO in plan steps. `payment_link` is explicitly a placeholder (`https://mygreenstar.org/pay/{tx_id}`) — consistent throughout.

**Type consistency:** `_qr_posted = pyqtSignal(str, str)` defined in Task 2, consumed as `worker.qr_posted.connect(self._qr_posted)` in Task 3 — consistent. `bus.crypto_session_changed = pyqtSignal(object)` defined in Task 1, emitted as `dict | None` everywhere — consistent.

---

## Web Page Plan (separate)

The `/enable-crypto/[kiosk_id]` Next.js page lives in the `kiosk-manager` repo. Create a separate plan there covering: route setup, Firestore write on "Enable Crypto Mode" button, `onSnapshot` listener, the five UI states, coin selector, "Add 1 minute" button, and QR code rendering from `payment_link`.
