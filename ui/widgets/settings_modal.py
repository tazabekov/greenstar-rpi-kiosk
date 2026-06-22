import os

from dotenv import set_key
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QWidget,
)

from core.bus import bus

_ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", ".env")

_INPUT = (
    "QLineEdit { background-color: #111111; color: #e8e8e8;"
    " border: 1px solid #333333; border-radius: 6px;"
    " font-size: 12pt; padding: 6px 10px; }"
    " QLineEdit:focus { border-color: #39ff14; }"
)
_LABEL = "color: #888888; font-size: 9pt; border: none;"
_SECTION = (
    "QPushButton { background-color: transparent; color: #555555;"
    " border: none; font-size: 10pt; text-align: left; padding: 4px 0; }"
    " QPushButton:hover { color: #888888; }"
)
_SAVE = (
    "QPushButton { background-color: #39ff14; color: #0d0d0d;"
    " border: none; border-radius: 6px;"
    " font-size: 13pt; font-weight: bold; }"
    " QPushButton:hover { background-color: #55ff33; }"
)
_CANCEL = (
    "QPushButton { background-color: #1a1a1a; color: #888888;"
    " border: 1px solid #333333; border-radius: 6px;"
    " font-size: 12pt; padding: 0 16px; }"
    " QPushButton:hover { border-color: #666666; color: #aaaaaa; }"
)


class SettingsModal(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        if parent:
            self.resize(parent.width(), parent.height())
            self.move(0, 0)
        self._advanced_visible = False
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget(self)
        card.setStyleSheet(
            "background-color: #0d0d0d;"
            " border: 2px solid #1a5c08; border-radius: 10px;"
        )
        card.setFixedWidth(420)
        card.setMaximumHeight((self.height() if self.height() > 0 else 480) - 40)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # ── Scrollable form area ──────────────────────────────────────
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent; border: none;")
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(14)

        title = QLabel("Kiosk Settings")
        title.setStyleSheet(
            "color: #39ff14; font-size: 15pt; font-weight: bold; border: none;"
        )
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Name
        layout.addWidget(self._field_label("Kiosk Name"))
        self._name_edit = QLineEdit(os.getenv("GKM_KIOSK_NAME", ""))
        self._name_edit.setFixedHeight(44)
        self._name_edit.setStyleSheet(_INPUT)
        self._name_edit.setPlaceholderText("e.g. Kiosk #1 – Main Floor")
        layout.addWidget(self._name_edit)

        # Location
        layout.addWidget(self._field_label("Location"))
        self._loc_edit = QLineEdit(os.getenv("GKM_KIOSK_LOCATION", ""))
        self._loc_edit.setFixedHeight(44)
        self._loc_edit.setStyleSheet(_INPUT)
        self._loc_edit.setPlaceholderText("e.g. Seattle, WA")
        layout.addWidget(self._loc_edit)

        # Advanced toggle
        self._adv_btn = QPushButton("▶  Advanced")
        self._adv_btn.setStyleSheet(_SECTION)
        self._adv_btn.clicked.connect(self._toggle_advanced)
        layout.addWidget(self._adv_btn)

        # Advanced section (hidden by default)
        self._adv_widget = QWidget()
        self._adv_widget.setStyleSheet("background: transparent;")
        adv_layout = QVBoxLayout(self._adv_widget)
        adv_layout.setContentsMargins(0, 0, 0, 0)
        adv_layout.setSpacing(8)

        adv_layout.addWidget(self._field_label("Kiosk ID"))
        self._id_edit = QLineEdit(os.getenv("GKM_KIOSK_ID", ""))
        self._id_edit.setFixedHeight(44)
        self._id_edit.setStyleSheet(_INPUT)
        self._id_edit.setPlaceholderText("e.g. 01-test-kiosk")
        adv_layout.addWidget(self._id_edit)

        warning = QLabel(
            "Each kiosk must have a unique ID. If you change this ID, the kiosk "
            "will appear as a new entry in the dashboard — historical data will "
            "remain under the previous ID and will not be merged."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "color: #aa7700; font-size: 9pt; border: 1px solid #3a2a00;"
            " border-radius: 5px; background: #1a1400; padding: 8px;"
        )
        adv_layout.addWidget(warning)

        self._adv_widget.hide()
        layout.addWidget(self._adv_widget)
        layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(scroll_content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 6px; background: #0a0a0a; }"
            "QScrollBar::handle:vertical { background: #2a2a2a; border-radius: 3px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        card_layout.addWidget(scroll, stretch=1)

        # ── Pinned button row ─────────────────────────────────────────
        btn_bar = QWidget()
        btn_bar.setStyleSheet(
            "background: transparent;"
            " border-top: 1px solid #1a2a1a;"
        )
        btn_row = QHBoxLayout(btn_bar)
        btn_row.setContentsMargins(24, 10, 24, 14)
        btn_row.setSpacing(10)

        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(44)
        cancel.setStyleSheet(_CANCEL)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        save = QPushButton("Save")
        save.setFixedHeight(44)
        save.setStyleSheet(_SAVE)
        save.clicked.connect(self._save)
        btn_row.addWidget(save, stretch=2)

        card_layout.addWidget(btn_bar)

        outer.addStretch()
        h_row = QHBoxLayout()
        h_row.addStretch()
        h_row.addWidget(card)
        h_row.addStretch()
        outer.addLayout(h_row)
        outer.addStretch()

    def _field_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(_LABEL)
        return lbl

    def _toggle_advanced(self):
        self._advanced_visible = not self._advanced_visible
        if self._advanced_visible:
            self._adv_widget.show()
            self._adv_btn.setText("▼  Advanced")
        else:
            self._adv_widget.hide()
            self._adv_btn.setText("▶  Advanced")

    def _save(self):
        name     = self._name_edit.text().strip()
        location = self._loc_edit.text().strip()
        kiosk_id = self._id_edit.text().strip()

        env = os.path.abspath(_ENV_PATH)
        if name:
            set_key(env, "GKM_KIOSK_NAME", name)
            os.environ["GKM_KIOSK_NAME"] = name
        if location:
            set_key(env, "GKM_KIOSK_LOCATION", location)
            os.environ["GKM_KIOSK_LOCATION"] = location
        if kiosk_id:
            set_key(env, "GKM_KIOSK_ID", kiosk_id)
            os.environ["GKM_KIOSK_ID"] = kiosk_id

        bus.settings_changed.emit(
            name     or os.getenv("GKM_KIOSK_NAME", ""),
            location or os.getenv("GKM_KIOSK_LOCATION", ""),
            kiosk_id or os.getenv("GKM_KIOSK_ID", ""),
        )
        self.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 180))
