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

    qr_posted = pyqtSignal(str, str)  # action_id, invoice_id

    def __init__(self, base_url, headers, device_id, kiosk_id, tx_id, amount, coin, bitpay_client, parent=None):
        super().__init__(parent)
        self._base_url      = base_url
        self._headers       = headers
        self._device_id     = device_id
        self._kiosk_id      = kiosk_id
        self._tx_id         = tx_id
        self._amount        = amount
        self._coin          = coin
        self._bitpay_client = bitpay_client

    def run(self):
        # Step 1: Create BitPay invoice to get the real payment URL
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
                        "barcode_contents": payment_url,
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
                      "payment_link": payment_url,
                      "amount_crypto": None,
                      "expires_at": expires_at,
                  })
            )
        except Exception as exc:
            log.warning("_CryptoQRWorker: Firestore write error: %s", exc)

        # Emit invoice_id so manager can poll status
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
    _payment_status_received = pyqtSignal(str)       # poll result from daemon thread

    def __init__(self, base_url, headers_fn, device_id, kiosk_id, bitpay_client, parent=None):
        super().__init__(parent)
        self._base_url      = base_url
        self._headers_fn    = headers_fn
        self._device_id     = device_id
        self._kiosk_id      = kiosk_id
        self._bitpay_client = bitpay_client

        self._session_id = None
        self._action_id  = None
        self._invoice_id = None

        self._expiry_timer = QTimer(self)
        self._expiry_timer.setSingleShot(True)
        self._expiry_timer.timeout.connect(self._on_expired)

        # Poll timer — fires every 5 s after QR is posted
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(5_000)
        self._poll_timer.timeout.connect(self._poll_payment_status)

        self._snapshot_received.connect(self._on_snapshot)
        self._qr_posted.connect(self._on_qr_posted)
        self._payment_status_received.connect(self._on_payment_status)
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
        self._poll_timer.stop()
        self._cancel_terminal_action()
        bus.crypto_mode = False
        bus.crypto_coin = ""
        self._session_id = None
        self._invoice_id = None
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
                "session_owner": "kiosk",
                "status":        "waiting_for_vend",
                "coin":          "BTC",
                "processor":     "bitpay",
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
            bitpay_client=self._bitpay_client,
        )
        worker.qr_posted.connect(self._qr_posted)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_qr_posted(self, action_id, invoice_id):
        self._action_id  = action_id
        self._invoice_id = invoice_id
        self._expiry_timer.stop()
        self._expiry_timer.start(60_000)
        if invoice_id:  # only poll when we have a valid invoice
            self._poll_timer.start()

    # ── Payment status polling ────────────────────────────────────────────

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
    from core.bitpay import make_bitpay_client

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

    bitpay_client = make_bitpay_client()
    return CryptoSessionManager(base_url, headers_fn, device_id, kiosk_id, bitpay_client, parent)
