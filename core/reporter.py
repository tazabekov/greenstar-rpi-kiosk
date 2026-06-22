"""
GKM Reporter — pushes heartbeats, metrics, and transactions to Firestore.

Requires firebase-admin and the following .env vars:
  FIREBASE_SERVICE_ACCOUNT_JSON  Firebase service-account key as a single-line JSON string
  GKM_KIOSK_ID                   unique kiosk identifier (e.g. "01-test-kiosk")
  GKM_KIOSK_NAME                 display name (e.g. "Santelli Starkey Ranch")
  GKM_KIOSK_LOCATION             location label (e.g. "Odessa, FL")

If firebase-admin is not installed or the env vars are missing, the reporter
starts in a no-op mode so the kiosk continues to run unaffected.
"""

import json
import logging
import os
from datetime import datetime, timezone

from PyQt5.QtCore import QObject, QTimer, pyqtSlot

log = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import credentials, firestore as fb_firestore
    _FB_AVAILABLE = True
except ImportError:
    _FB_AVAILABLE = False


def _now_utc():
    return datetime.now(timezone.utc)


class Reporter(QObject):
    """Syncs kiosk state to Firestore every 60 s and on each transaction event."""

    HEARTBEAT_INTERVAL_MS = 60_000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db = None
        self._kiosk_id = None
        self._kiosk_ref = None
        self._cpu = 0.0
        self._temp = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(self.HEARTBEAT_INTERVAL_MS)
        self._timer.timeout.connect(self._heartbeat)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def start(self):
        if not _FB_AVAILABLE:
            log.warning("Reporter: firebase-admin not installed — GKM reporting disabled")
            return

        sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
        self._kiosk_id = os.getenv("GKM_KIOSK_ID", "")
        if not sa_json or not self._kiosk_id:
            log.warning("Reporter: FIREBASE_SERVICE_ACCOUNT_JSON / GKM_KIOSK_ID not set — disabled")
            return

        try:
            cred = credentials.Certificate(json.loads(sa_json))
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            self._db = fb_firestore.client()
            self._kiosk_ref = self._db.collection("kiosks").document(self._kiosk_id)
            log.info("Reporter: connected to Firestore as kiosk %s", self._kiosk_id)
        except Exception:
            log.exception("Reporter: failed to initialise Firebase — disabled")
            return

        # Fire immediately then every 60 s
        self._heartbeat()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    # ------------------------------------------------------------------ #
    # Slots — wired to AppBus signals in main.py                          #
    # ------------------------------------------------------------------ #

    @pyqtSlot(float)
    def on_cpu_sample(self, value: float):
        self._cpu = value

    @pyqtSlot(float)
    def on_temp_sample(self, value: float):
        self._temp = value

    @pyqtSlot(object)
    def on_transaction_added(self, tx):
        if not self._kiosk_ref:
            return
        try:
            self._kiosk_ref.collection("transactions").document(tx.tx_id).set(
                self._tx_to_dict(tx), merge=True
            )
        except Exception:
            log.exception("Reporter: failed to sync transaction %s", tx.tx_id)

    @pyqtSlot(str, str, str)
    def on_settings_changed(self, name: str, location: str, kiosk_id: str):
        if not self._db:
            return
        if kiosk_id and kiosk_id != self._kiosk_id:
            self._kiosk_id = kiosk_id
            self._kiosk_ref = self._db.collection("kiosks").document(kiosk_id)
            log.info("Reporter: kiosk ID updated to %s", kiosk_id)
        # Push updated name/location immediately
        self._heartbeat()

    @pyqtSlot(str, object)
    def on_transaction_event(self, tx_id: str, event):
        if not self._kiosk_ref:
            return
        try:
            self._kiosk_ref.collection("transactions").document(tx_id).set(
                {"events": fb_firestore.ArrayUnion([self._event_to_dict(event)])},
                merge=True,
            )
        except Exception:
            log.exception("Reporter: failed to append event to tx %s", tx_id)

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _heartbeat(self):
        if not self._kiosk_ref:
            return
        try:
            now = _now_utc()
            snapshot = self._kiosk_ref.get()
            if not snapshot.exists:
                self._kiosk_ref.set({
                    "kiosk_id": self._kiosk_id,
                    "name": os.getenv("GKM_KIOSK_NAME", self._kiosk_id),
                    "location": os.getenv("GKM_KIOSK_LOCATION", ""),
                    "registered_at": now,
                    "last_heartbeat": now,
                    "cpu_percent": self._cpu,
                    "temperature_c": self._temp,
                })
                log.info("Reporter: kiosk registered in Firestore")
            else:
                self._kiosk_ref.update({
                    "last_heartbeat": now,
                    "cpu_percent": self._cpu,
                    "temperature_c": self._temp,
                    "name": os.getenv("GKM_KIOSK_NAME", self._kiosk_id),
                    "location": os.getenv("GKM_KIOSK_LOCATION", ""),
                })

            self._kiosk_ref.collection("metrics").add({
                "cpu_percent": self._cpu,
                "temperature_c": self._temp,
                "recorded_at": now,
            })
        except Exception:
            log.exception("Reporter: heartbeat failed — will retry next cycle")

    @staticmethod
    def _tx_to_dict(tx) -> dict:
        return {
            "tx_id": tx.tx_id,
            "item": tx.item,
            "amount": tx.amount,
            "payment_type": tx.payment_type,
            "status": tx.status,
            "time": tx.time.astimezone(timezone.utc) if tx.time.tzinfo else
                    tx.time.replace(tzinfo=timezone.utc),
            "events": [Reporter._event_to_dict(e) for e in tx.events],
        }

    @staticmethod
    def _event_to_dict(event) -> dict:
        return {
            "timestamp": event.timestamp.astimezone(timezone.utc) if event.timestamp.tzinfo else
                         event.timestamp.replace(tzinfo=timezone.utc),
            "source": event.source,
            "direction": event.direction,
            "message": event.message,
            "raw": event.raw,
        }
