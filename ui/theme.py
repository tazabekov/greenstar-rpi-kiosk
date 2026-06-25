from PyQt5.QtGui import QColor

# Palette
BG_DARK      = QColor("#0d0d0d")
PANEL_BG     = QColor("#111111")
BORDER_DIM   = QColor("#1a5c08")
ACCENT_GREEN = QColor("#39ff14")
TEMP_LINE    = QColor("#00c8ff")
TEXT_WHITE   = QColor("#e8e8e8")
TEXT_MID     = QColor("#909090")
TEXT_DIM     = QColor("#555555")

# Time-window presets (label, sample-count at 2 s base rate)
WINDOWS = [
    ("1 min",  30),
    ("5 min",  150),
    ("1 hr",   1_800),
    ("24 hr",  43_200),
]

# Button stylesheets (applied directly via setStyleSheet — avoids Qt cascade bugs)
BTN_ACTIVE = (
    "QPushButton { background-color: #39ff14; color: #0d0d0d;"
    " border: 2px solid #39ff14; border-radius: 8px;"
    " font-size: 13pt; font-weight: bold; padding: 6px 0px; }"
)
BTN_INACTIVE = (
    "QPushButton { background-color: #111111; color: #39ff14;"
    " border: 2px solid #1a5c08; border-radius: 8px;"
    " font-size: 13pt; font-weight: bold; padding: 6px 0px; }"
    " QPushButton:hover { border-color: #39ff14; background-color: #0d1f08; }"
)

BTN_PRIMARY = (
    "QPushButton { background-color: #0d1f08; color: #39ff14;"
    " border: 2px solid #39ff14; border-radius: 8px;"
    " font-size: 14pt; font-weight: bold; padding: 8px 0px; }"
    " QPushButton:hover { background-color: #152b0a; }"
    " QPushButton:pressed { background-color: #39ff14; color: #0d0d0d; }"
)

GLOBAL_STYLESHEET = """
QWidget {
    background-color: #0d0d0d;
    color: #e8e8e8;
    font-family: "DejaVu Sans", sans-serif;
}
QDialog {
    background-color: #0d0d0d;
}
"""
