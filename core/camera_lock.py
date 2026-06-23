"""
Shared lock that serialises access to the single OV5647 camera.

Both CameraModal (live preview) and Snapshotter (periodic still) must
acquire this lock before constructing a Picamera2 instance.  The holder
releases it only after cam.stop() + cam.close() complete.

Usage (non-blocking try):
    if camera_lock.acquire(blocking=False):
        try:
            ...open and use camera...
        finally:
            camera_lock.release()
    else:
        # camera busy — skip this cycle
"""
import threading

camera_lock = threading.Lock()
