"""
Snapshotter — periodic multi-camera capture + Firebase Storage upload.

Every GKM_SNAPSHOT_INTERVAL_MIN minutes, discovers all attached cameras via
CameraRegistry.probe() and captures a JPEG from each, uploading to Firebase
Storage at:
  kiosks/{kiosk_id}/camera0/last-snapshot.jpg
  kiosks/{kiosk_id}/camera1/last-snapshot.jpg
  kiosks/{kiosk_id}/camera2/last-snapshot.jpg
  ... (one per detected camera)

After a successful upload, updates the kiosk Firestore document with:
  last_snapshot_path           — Storage path for camera 0 (backward-compat)
  last_snapshot_path_camera1   — Storage path for camera 1 (if present)
  last_snapshot_path_camera2   — Storage path for camera 2 (if present)
  ... (one field per camera)
  last_snapshot_at             — server timestamp

If a camera is already in use (e.g. CameraModal is open), that camera's
snapshot is silently skipped and retried at the next scheduled interval.
Uses core/camera_registry.py per-camera locks to prevent concurrent access.

Requires in .env:
  GKM_FIREBASE_STORAGE_BUCKET   e.g. myproject.appspot.com
  GKM_SNAPSHOT_INTERVAL_MIN     integer ≥ 1; 0 = disabled
  GKM_KIOSK_ID                  used as the Firestore/Storage path key
"""

import logging
import os
import tempfile
import threading
import time

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
        from core.camera_registry import registry
        cameras = registry.cameras()

        if not cameras:
            with self._lock:
                self._thread_running = False
            QTimer.singleShot(0, self._schedule)
            return

        results: dict[int, str | None] = {}
        results_lock = threading.Lock()

        def _capture_one(info):
            path = self._capture_and_upload(info)
            with results_lock:
                results[info.idx] = path

        threads = [
            threading.Thread(target=_capture_one, args=(info,), daemon=True)
            for info in cameras
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        captured = {idx: path for idx, path in results.items() if path is not None}
        if not captured:
            with self._lock:
                self._thread_running = False
            QTimer.singleShot(0, self._schedule)
            return

        try:
            updates: dict = {"last_snapshot_at": fb_firestore.SERVER_TIMESTAMP}
            for idx, storage_path in sorted(captured.items()):
                if idx == 0:
                    updates["last_snapshot_path"] = storage_path
                else:
                    updates[f"last_snapshot_path_camera{idx}"] = storage_path
            self._kiosk_ref.update(updates)
        except Exception:
            log.exception("Snapshotter: Firestore update failed — will retry next interval")
        finally:
            with self._lock:
                self._thread_running = False
            QTimer.singleShot(0, self._schedule)

    def _capture_and_upload(self, info) -> str | None:
        """Capture JPEG from one camera and upload to Storage. Returns Storage path or None."""
        tmp_path = self._capture_jpeg(info)
        if tmp_path is None:
            return None
        storage_path = f"kiosks/{self._kiosk_id}/camera{info.idx}/last-snapshot.jpg"
        try:
            bucket = fb_storage.bucket(self._bucket_name)
            blob = bucket.blob(storage_path)
            blob.upload_from_filename(tmp_path, content_type="image/jpeg")
            log.info("Snapshotter: uploaded %s", storage_path)
            return storage_path
        except Exception:
            log.exception("Snapshotter: upload of camera%d failed", info.idx)
            return None
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _capture_jpeg(self, info) -> str | None:
        """Capture one still frame from info.idx and save to a temp JPEG. Returns path or None."""
        from core.camera_registry import registry

        # If the live feed is already running, capture directly from it.
        # AE/AWB is already converged — no lock acquisition or sleep needed.
        running_cam = registry.get_running_cam(info.idx)
        if running_cam is not None:
            fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            try:
                running_cam.capture_file(tmp_path)
                log.info("Snapshotter: captured from running stream camera %d", info.idx)
                return tmp_path
            except Exception as exc:
                log.warning(
                    "Snapshotter: camera %d live-capture failed (%s) — skipping", info.idx, exc
                )
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                return None

        # Camera is idle — start our own instance.
        if not registry.acquire(info.idx, blocking=False):
            log.info("Snapshotter: camera %d in use — skipping", info.idx)
            return None
        fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        try:
            from picamera2 import Picamera2
            cam = Picamera2(info.idx)
            cfg = cam.create_preview_configuration(
                main={"size": (info.max_w, info.max_h), "format": "RGB888"}
            )
            cam.configure(cfg)
            cam.start()
            time.sleep(2)
            cam.capture_file(tmp_path)
            cam.stop()
            cam.close()
            return tmp_path
        except Exception as exc:
            log.warning(
                "Snapshotter: camera %d capture failed (%s) — skipping", info.idx, exc
            )
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return None
        finally:
            registry.release(info.idx)
