# Multi-Camera Support Design

**Date:** 2026-06-23  
**Status:** Approved

## Problem

Camera index (`0`) and resolution (`2592×1944`) are hardcoded to the Arducam OV5647.
Different kiosks may have different cameras. When multiple cameras are attached the
app currently ignores all but camera 0 and provides no way to view or snapshot the
others.

## Goals

1. Discover all attached cameras dynamically at startup.
2. Query each camera's max resolution without hardcoding.
3. Camera modal shows a live feed per camera with model name and resolution in the status bar.
4. Snapshotter captures a still from every camera on each tick and uploads each to a separate Firebase Storage path.

## Out of Scope

- Camera switching / reordering preferences
- Per-camera snapshot intervals
- Remote camera control

---

## Architecture

### `core/camera_registry.py` (new)

Replaces `core/camera_lock.py`.

```
CameraInfo
  idx: int        — camera index (0, 1, …)
  model: str      — e.g. "ov5647", "imx219"
  max_w: int      — full sensor width
  max_h: int      — full sensor height

CameraRegistry
  probe() -> None
    — calls Picamera2.global_camera_info()
    — for each result: opens Picamera2(idx), reads
      camera_properties['PixelArraySize'], closes it
    — stores CameraInfo + threading.Lock per camera
    — no-op if picamera2 not installed

  cameras() -> list[CameraInfo]
  acquire(idx, blocking=False) -> bool
  release(idx) -> None

registry = CameraRegistry()   # module-level singleton
```

`main.py` calls `registry.probe()` once at startup, replacing the current
`Picamera2.global_camera_info()` call. All downstream code imports from
`core.camera_registry`.

`core/camera_lock.py` is deleted.

---

### `ui/widgets/camera_modal.py` (rewritten)

Introduces a private `_CameraFeedPanel` inner class. Each panel owns one camera:

- Holds the `Picamera2` instance, `_running` flag, `_frame_ready` / `_feed_error` signals
- `_on_frame` callback throttles to ~15 fps, emits pre-scaled `QImage` via signal
- Status bar text: `"{model} · {max_w}×{max_h} · ● Live"` when running, error text on failure
- `start()` / `stop()` methods; `stop()` runs `cam.stop()/close()` in a daemon thread and releases the per-camera lock

`CameraModal` reads `registry.cameras()` in `showEvent` and builds layout:

| Camera count | Layout |
|---|---|
| 0 | Single card: "No camera detected" |
| 1 | Single `_CameraFeedPanel` filling the card |
| 2 | `QHBoxLayout` — two panels side by side |
| 3+ | `QTabWidget` — one tab per camera, labelled with model name |

All panels are started in `showEvent` and stopped in `closeEvent` regardless of layout.
Each panel acquires its own per-camera lock; failure to acquire shows "Camera busy" in
that panel's status bar without affecting other panels.

---

### `core/snapshotter.py` (updated)

`_do_snapshot` spawns one worker thread per camera (parallel). Each thread:

1. Tries `registry.acquire(idx, blocking=False)` — skips if locked (modal open on that camera).
2. Opens `Picamera2(idx)`, configures with `create_preview_configuration` at `max_w × max_h`.
3. Waits 2 s for AE/AWB convergence.
4. Captures to a temp JPEG, closes the camera, releases the lock.
5. Uploads to `kiosks/{kiosk_id}/camera{idx}/last-snapshot.jpg`.

All threads are joined before the Firestore update, which writes in one call:

```
last_snapshot_at            — server timestamp (existing field, dashboard reads this)
last_snapshot_path          — path for camera 0 (backward-compatible)
last_snapshot_path_camera1  — path for camera 1 (new; omitted if not present)
last_snapshot_path_camera2  — path for camera 2 (new; omitted if not present)
…
```

If every camera was skipped (all busy), the tick is silently skipped as before.

---

## Firebase Storage Paths

```
kiosks/{kiosk_id}/camera0/last-snapshot.jpg   ← always (if camera 0 captured)
kiosks/{kiosk_id}/camera1/last-snapshot.jpg   ← if camera 1 present and captured
```

---

## Tests

### `tests/test_camera_registry.py` (new)

- `probe()` with mocked `Picamera2`: verifies correct `CameraInfo` fields
- Per-camera locks are independent (acquiring camera 0 does not block camera 1)
- `probe()` is a no-op when picamera2 import fails

### `tests/test_camera_modal.py` (updated)

- Mock `registry.cameras()` returning 0, 1, 2 cameras; verify correct panel count and layout type
- Existing `_running` / close / signal tests carried over, scoped to single-camera case

---

## File Changes

| File | Change |
|---|---|
| `core/camera_registry.py` | NEW |
| `core/camera_lock.py` | DELETED |
| `ui/widgets/camera_modal.py` | Rewritten |
| `core/snapshotter.py` | Updated |
| `main.py` | `registry.probe()` replaces `global_camera_info()` |
| `tests/test_camera_registry.py` | NEW |
| `tests/test_camera_modal.py` | Updated |
| `README.md` | Updated — file map, camera section |
