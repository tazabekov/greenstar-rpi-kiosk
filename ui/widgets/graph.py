import math
from collections import deque

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QFont, QLinearGradient, QPolygonF, QPainterPath,
)
from PyQt5.QtWidgets import QWidget

from ui.theme import PANEL_BG, BORDER_DIM, TEXT_MID, TEXT_DIM

MAX_POINTS  = 43_200   # 24 h × 3600 s / 2 s per sample
MAX_DISPLAY = 400      # segments actually drawn — large windows are decimated

SAMPLE_S = 2           # DataSampler base rate in seconds


# ── Y-axis helpers ────────────────────────────────────────────────────────────

def _nice_axis(data_lo, data_hi, min_span=20, n_ticks=4):
    """Return (axis_lo, axis_hi, tick_values) with round, readable numbers."""
    span = max(data_hi - data_lo, min_span)
    pad  = span * 0.20
    lo, hi = data_lo - pad, data_hi + pad

    raw_step  = (hi - lo) / n_ticks
    magnitude = 10 ** math.floor(math.log10(max(raw_step, 1e-9)))
    step = magnitude
    for mult in (1, 2, 2.5, 5, 10):
        step = mult * magnitude
        if step >= raw_step:
            break

    lo = math.floor(lo / step) * step
    hi = math.ceil(hi  / step) * step

    ticks, v = [], lo
    while v <= hi + step * 0.01:
        ticks.append(round(v, 6))
        v += step
    return lo, hi, ticks


# ── Temperature colour ramp ───────────────────────────────────────────────────

def _temp_color(value):
    """Green → amber → red mapped to RPi5 thermal thresholds."""
    if value <= 50:
        return QColor("#39ff14")
    elif value <= 65:
        t = (value - 50) / 15.0
        return QColor(
            int(0x39 + t * (0xf0 - 0x39)),
            int(0xff + t * (0xa0 - 0xff)),
            int(0x14 + t * (0x00 - 0x14)),
        )
    elif value <= 80:
        t = (value - 65) / 15.0
        return QColor(
            int(0xf0 + t * (0xff - 0xf0)),
            int(0xa0 + t * (0x22 - 0xa0)),
            int(0x00 + t * (0x44 - 0x00)),
        )
    return QColor("#ff2244")


# ── Misc helpers ──────────────────────────────────────────────────────────────

def _downsample(seq, max_pts):
    n = len(seq)
    if n <= max_pts:
        return seq
    step = n / max_pts
    result = [seq[int(i * step)] for i in range(max_pts)]
    result[-1] = seq[-1]  # always include the newest sample
    return result


def _fmt_dur(seconds):
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m" if s == 0 else f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h" if m == 0 else f"{h}h{m:02d}m"


# ── Widget ────────────────────────────────────────────────────────────────────

class GraphWidget(QWidget):
    def __init__(self, title, unit, line_color,
                 min_span=20, anchor_zero=False, heat_color=False,
                 parent=None):
        super().__init__(parent)
        self.title       = title
        self.unit        = unit
        self.line_color  = line_color   # baseline / cold colour; also fill colour
        self.min_span    = min_span
        self.anchor_zero = anchor_zero  # keep lo ≥ 0 (CPU %)
        self.heat_color  = heat_color   # draw segments with _temp_color()
        self.data        = deque(maxlen=MAX_POINTS)
        self.window_samples = 150       # default: 5 min at 2 s
        self.setMinimumHeight(100)

    def push(self, value):
        self.data.append(value)
        self.update()

    def set_window(self, n_samples):
        self.window_samples = n_samples
        self.update()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        left, right, top, bottom = 58, 10, 52, 32
        plot_w = w - left - right
        plot_h = h - top - bottom

        # Panel background + accent bar + border
        painter.fillRect(0, 0, w, h, PANEL_BG)
        cur_col = _temp_color(self.data[-1]) if (self.heat_color and self.data) \
                  else self.line_color
        painter.fillRect(0, 0, 4, h, cur_col)
        painter.setPen(QPen(BORDER_DIM, 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        # Scan-line texture
        scanline = QColor(0, 0, 0, 45)
        painter.setPen(Qt.NoPen)
        for row in range(0, plot_h, 4):
            painter.fillRect(left, top + row, plot_w, 2, scanline)

        # Slice + downsample
        raw     = list(self.data)[-self.window_samples:]
        visible = _downsample(raw, MAX_DISPLAY)

        # Auto-range Y axis
        if visible:
            lo, hi, ticks = _nice_axis(min(visible), max(visible), self.min_span)
            if self.anchor_zero:
                lo = 0
                ticks = [t for t in ticks if t >= 0]
        else:
            lo, hi, ticks = (0, 100, [0, 25, 50, 75, 100]) if self.anchor_zero \
                            else (30, 90, [30, 50, 70, 90])

        y_range = max(hi - lo, 1e-9)

        # Grid lines + y-axis labels
        painter.setFont(QFont("DejaVu Sans", 11))
        for val in ticks:
            ry = (val - lo) / y_range
            sy = int(top + plot_h - ry * plot_h)
            if not (top - 5 <= sy <= top + plot_h + 5):
                continue
            painter.setPen(QPen(BORDER_DIM, 1, Qt.DotLine))
            painter.drawLine(left, sy, left + plot_w, sy)
            painter.setPen(QPen(TEXT_MID, 1))
            lbl = f"{int(val)}{self.unit}" if val == int(val) \
                  else f"{val:.1f}{self.unit}"
            painter.drawText(4, sy - 9, left - 8, 20,
                             Qt.AlignRight | Qt.AlignVCenter, lbl)

        # Title (small, understated)
        painter.setFont(QFont("DejaVu Sans", 9))
        painter.setPen(QPen(TEXT_MID))
        painter.drawText(left + 6, 4, plot_w // 2, 18,
                         Qt.AlignLeft | Qt.AlignTop, self.title)

        # Current value — hero number
        if self.data:
            painter.setFont(QFont("DejaVu Sans", 28, QFont.Bold))
            painter.setPen(QPen(cur_col))
            painter.drawText(left, 4, plot_w - 4, top - 8,
                             Qt.AlignRight | Qt.AlignVCenter,
                             f"{self.data[-1]:.1f}{self.unit}")

        if len(visible) < 2:
            painter.setPen(QPen(TEXT_DIM))
            painter.setFont(QFont("DejaVu Sans", 10))
            painter.drawText(left, top, plot_w, plot_h,
                             Qt.AlignCenter, "Collecting data…")
            painter.end()
            return

        n = len(visible)
        x_step = plot_w / (n - 1)

        def to_pt(i, val):
            sx = left + i * x_step
            clamped = max(lo, min(hi, val))
            sy = top + plot_h - (clamped - lo) / y_range * plot_h
            return QPointF(sx, sy)

        points = [to_pt(i, v) for i, v in enumerate(visible)]

        # Area fill (always uses cold/baseline colour, fades to transparent)
        path = QPainterPath()
        path.moveTo(points[0].x(), top + plot_h)
        path.lineTo(points[0])
        for pt in points[1:]:
            path.lineTo(pt)
        path.lineTo(points[-1].x(), top + plot_h)
        path.closeSubpath()

        fill = QColor(self.line_color); fill.setAlpha(60)
        fade = QColor(self.line_color); fade.setAlpha(0)
        grad = QLinearGradient(0, top, 0, top + plot_h)
        grad.setColorAt(0.0, fill)
        grad.setColorAt(1.0, fade)
        painter.setBrush(grad)
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)

        # Line — coloured segments (temp) or solid (CPU)
        painter.setBrush(Qt.NoBrush)
        if self.heat_color:
            for i in range(len(points) - 1):
                seg_color = _temp_color((visible[i] + visible[i + 1]) / 2)
                painter.setPen(QPen(seg_color, 2, Qt.SolidLine,
                                    Qt.RoundCap, Qt.RoundJoin))
                painter.drawLine(points[i], points[i + 1])
        else:
            painter.setPen(QPen(self.line_color, 2, Qt.SolidLine,
                                Qt.RoundCap, Qt.RoundJoin))
            painter.drawPolyline(QPolygonF(points))

        # X-axis time labels
        window_s = len(raw) * SAMPLE_S
        tick_y   = top + plot_h

        painter.setPen(QPen(QColor("#444444"), 1))
        for x in (left, left + plot_w // 2, left + plot_w):
            painter.drawLine(int(x), tick_y, int(x), tick_y + 4)

        painter.setFont(QFont("DejaVu Sans", 8))
        painter.setPen(QPen(QColor("#555555")))
        lbl_y = tick_y + 5
        painter.drawText(left,                   lbl_y, 80, 14,
                         Qt.AlignLeft,   f"−{_fmt_dur(window_s)}")
        painter.drawText(left + plot_w//2 - 40,  lbl_y, 80, 14,
                         Qt.AlignCenter, f"−{_fmt_dur(window_s / 2)}")
        painter.drawText(left + plot_w - 40,     lbl_y, 40, 14,
                         Qt.AlignRight,  "now")

        painter.end()
