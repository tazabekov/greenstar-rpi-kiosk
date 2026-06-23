"""
Snapshotter — periodic camera capture + Firebase Storage upload.

Every GKM_SNAPSHOT_INTERVAL_MIN minutes, captures a JPEG from the OV5647
camera and uploads it to Firebase Storage at:
  kiosks/{kiosk_id}/camera0/last-snapshot.jpg

After a successful upload, updates the kiosk Firestore document with:
  last_snapshot_path  — Storage path (string)
  last_snapshot_at    — server timestamp

If the camera is already in use (e.g. CameraModal is open), the snapshot
is silently skipped and retried at the next scheduled interval.

Requires in .env:
  GKM_FIREBASE_STORAGE_BUCKET   e.g. myproject.appspot.com
  GKM_SNAPSHOT_INTERVAL_MIN     integer ≥ 1; 0 = disabled
  GKM_KIOSK_ID                  used as the Firestore/Storage path key
"""

import logging
import os
import tempfile
import threading

from PyQt5.QtCore import QObject, QTimer, pyqtSlot

log = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import firestore as fb_firestore, storage as fb_storage
    _FB_AVAILABLE = True
except ImportError:
    _FB_AVAILABLE = False


class Snapshotter(QObject):
    """Periodic camera-to-Firebase-Storage snapshot service."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._interval_min = 0
        self._bucket_name  = ""
        self._kiosk_id     = ""
        self._kiosk_ref    = None

        # Single-shot so pile-up is impossible if upload outlasts the interval
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)

        self._lock           = threading.Lock()
        self._thread_running = False

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def start(self):
        if not _FB_AVAILABLE:
            log.warning("Snapshotter: firebase-admin not installed — disabled")
            return

        self._bucket_name  = os.getenv("GKM_FIREBASE_STORAGE_BUCKET", "")
        self._kiosk_id     = os.getenv("GKM_KIOSK_ID", "")
        self._interval_min = int(os.getenv("GKM_SNAPSHOT_INTERVAL_MIN", "0") or "0")

        if not self._bucket_name or not self._kiosk_id:
            log.warning(
                "Snapshotter: GKM_FIREBASE_STORAGE_BUCKET or GKM_KIOSK_ID not set — disabled"
            )
            return

        if not firebase_admin._apps:
            log.warning("Snapshotter: firebase_admin not yet initialised — disabled")
            return

        try:
            db = fb_firestore.client()
            self._kiosk_ref = db.collection("kiosks").document(self._kiosk_id)
        except Exception:
            log.exception("Snapshotter: failed to get Firestore client — disabled")
            return

        log.info("Snapshotter: started (interval=%d min)", self._interval_min)
        self._schedule()

    def stop(self):
        self._timer.stop()

    @pyqtSlot(int)
    def set_interval(self, minutes: int):
        self._interval_min = minutes
        os.environ["GKM_SNAPSHOT_INTERVAL_MIN"] = str(minutes)
        self._timer.stop()
        self._schedule()
        log.info("Snapshotter: interval updated to %d min", minutes)

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _schedule(self):
        if self._interval_min <= 0 or self._kiosk_ref is None:
            return
        self._timer.start(self._interval_min * 60_000)

    def _on_timer(self):
        with self._lock:
            if self._thread_running:
                log.info("Snapshotter: previous snapshot still running — skipping tick")
                self._schedule()
                return
            self._thread_running = True
        t = threading.Thread(target=self._do_snapshot, daemon=True)
        t.start()

    def _do_snapshot(self):
        tmp_path = self._capture_jpeg()
        if tmp_path is None:
            # Camera was busy or errored — skip this interval
            with self._lock:
                self._thread_running = False
            QTimer.singleShot(0, self._schedule)
            return
        try:
            path = f"kiosks/{self._kiosk_id}/camera0/last-snapshot.jpg"
            bucket = fb_storage.bucket(self._bucket_name)
            blob = bucket.blob(path)
            blob.upload_from_filename(tmp_path, content_type="image/jpeg")
            log.info("Snapshotter: uploaded snapshot to %s", path)
            self._kiosk_ref.update({
                "last_snapshot_path": path,
                "last_snapshot_at":   fb_firestore.SERVER_TIMESTAMP,
            })
        except Exception:
            log.exception("Snapshotter: upload/Firestore update failed — will retry next interval")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            with self._lock:
                self._thread_running = False
            QTimer.singleShot(0, self._schedule)

    def _capture_jpeg(self) -> str | None:
        """Capture one still frame and save to a temp JPEG. Returns path or None."""
        from core.camera_lock import camera_lock
        if not camera_lock.acquire(blocking=False):
            log.info("Snapshotter: camera in use (CameraModal open) — skipping")
            return None
        fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        try:
            from picamera2 import Picamera2
            cam = Picamera2(0)
            cfg = cam.create_still_configuration(
                main={"size": (1920, 1080), "format": "RGB888"}
            )
            cam.configure(cfg)
            cam.start()
            cam.capture_file(tmp_path)
            cam.stop()
            cam.close()
            return tmp_path
        except Exception as exc:
            log.warning("Snapshotter: camera capture failed (%s) — skipping", exc)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return None
        finally:
            camera_lock.release()
