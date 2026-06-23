import logging
import threading
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class CameraInfo:
    idx: int
    model: str
    max_w: int
    max_h: int


class CameraRegistry:
    def __init__(self):
        self._cameras: list[CameraInfo] = []
        self._locks: dict[int, threading.Lock] = {}

    def probe(self) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError:
            log.warning("CameraRegistry: picamera2 not installed — no cameras")
            return

        raw = Picamera2.global_camera_info()
        for cam_dict in raw:
            idx = cam_dict["Num"]
            model = cam_dict.get("Model", f"camera{idx}")
            try:
                cam = Picamera2(idx)
                w, h = cam.camera_properties["PixelArraySize"]
                cam.close()
            except Exception as exc:
                log.warning(
                    "CameraRegistry: failed to probe camera %d (%s) — skipping", idx, exc
                )
                continue
            self._cameras.append(CameraInfo(idx=idx, model=model, max_w=w, max_h=h))
            self._locks[idx] = threading.Lock()
            log.info("CameraRegistry: camera %d — %s %dx%d", idx, model, w, h)

    def cameras(self) -> list[CameraInfo]:
        return list(self._cameras)

    def acquire(self, idx: int, blocking: bool = False) -> bool:
        lock = self._locks.get(idx)
        if lock is None:
            return False
        return lock.acquire(blocking=blocking)

    def release(self, idx: int) -> None:
        lock = self._locks.get(idx)
        if lock is not None:
            try:
                lock.release()
            except RuntimeError:
                pass


registry = CameraRegistry()
