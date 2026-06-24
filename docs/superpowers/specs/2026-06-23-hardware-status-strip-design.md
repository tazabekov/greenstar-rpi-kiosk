# Hardware Status Strip — Design Spec
**Date:** 2026-06-23  
**Status:** Approved

## Goal

Add throttle status, fan level, and disk usage to the System screen so operators can detect silent hardware degradation (thermal throttling, dead fan, full disk) at a glance.

## Layout

A 60px horizontal strip inserted between the two time-series graphs and the existing button bar on `SystemScreen`:

```
┌─────────────────────────────────────────────────────────────────┐
│ CPU graph  (stretch=1, shrinks slightly)                        │
├─────────────────────────────────────────────────────────────────┤
│ Temp graph (stretch=1, shrinks slightly)                        │
├──────────────────┬───────────────────┬──────────────────────────┤
│ THROTTLE  ● OK   │  FAN  Level 2/7   │  DISK  34.2%            │
│                  │  ██████░░░░░░░░░  │  █████████░░░░░░░░░░░   │
├──────────────────┴───────────────────┴──────────────────────────┤
│  [1 min]  [5 min]  [1 hr]  [24 hr]                             │
└─────────────────────────────────────────────────────────────────┘
```

Each panel is ~267px wide × 60px tall, painted via QPainter (consistent with existing widget style).

## Data Sources

| Metric | Source | Fallback |
|--------|--------|----------|
| Throttle | `vcgencmd get_throttled` → hex bitmask | 0 (OK) if binary absent |
| Fan level | `/sys/class/thermal/cooling_device0/cur_state` | -1 (N/A) if path missing |
| Disk usage | `psutil.disk_usage('/').percent` | 0.0 on OSError |

Sampled every 2 s in `DataSampler._sample()`, same as CPU/temp.

## Throttle Bitmask Decoding

`vcgencmd get_throttled` returns e.g. `throttled=0x50000`.

| Bit | Meaning | Severity |
|-----|---------|----------|
| 0 | Under-voltage now | Critical (red) |
| 1 | ARM freq cap active | Warning (amber) |
| 2 | Currently throttled | Critical (red) |
| 3 | Soft temp limit active | Warning (amber) |
| 16–19 | Same flags, ever since boot | Info (dim) |

Display: green "● OK" when bitmask == 0. Otherwise show the highest-severity active flag label. Bits 16–19 (historical) shown as a dim secondary line if set but no current flags.

## Components

### `core/sampler.py` changes
- Add signals: `fan_sample = pyqtSignal(int)`, `disk_sample = pyqtSignal(float)`, `throttle_sample = pyqtSignal(int)`
- In `_sample()`: read fan sysfs path, `psutil.disk_usage`, and `subprocess` call to `vcgencmd` (with `timeout=1`). All wrapped in try/except with safe fallbacks.
- `vcgencmd` is called via `subprocess.run` with `capture_output=True`; parse `throttled=0x...` from stdout.

### `ui/widgets/hardware_status.py` (new file)
Single public class: `HardwareStatusBar(QWidget)`.  
Internally three `QWidget` subclasses painted via `paintEvent`:
- `_ThrottlePanel` — title "THROTTLE", colored status dot + label, dim historical line
- `_FanPanel` — title "FAN", "Level N/7" hero text, progress bar
- `_DiskPanel` — title "DISK", "XX.X%" hero text, progress bar

All three use the existing palette (`PANEL_BG`, `BORDER_DIM`, `ACCENT_GREEN`, `TEXT_MID`, `TEXT_DIM`) from `ui/theme.py`. No new colors needed — amber is constructed inline (`QColor("#f0a000")`) for warnings; red reuses the existing heat-map red `QColor("#ff2244")`.

Public interface:
```python
bar = HardwareStatusBar()
bar.push_throttle(int)   # raw bitmask
bar.push_fan(int)        # level 0–N, or -1 for N/A
bar.push_disk(float)     # percent 0–100
```

### `ui/screens/system.py` changes
- Import and instantiate `HardwareStatusBar`
- Add it to root layout with `setFixedHeight(60)` between the temp graph and the button bar
- Extend `wire_sampler()` to connect the three new signals

### Tests
- `tests/test_sampler.py`: patch sysfs read and `subprocess.run`; assert new signals fire with expected values; assert fallbacks return safe values when sources are unavailable.
- `tests/test_hardware_status.py`: smoke-test that `HardwareStatusBar` renders without crash for all combinations (OK, each warning bit set, N/A fan, disk 0 and 100%).

## Non-Goals
- No time-series graphing for fan/disk/throttle (values change too slowly to be useful as graphs)
- Dashboard `SystemMiniPanel` unchanged — new metrics on System screen only
- No Watts / power reading (requires external hardware shunt)
