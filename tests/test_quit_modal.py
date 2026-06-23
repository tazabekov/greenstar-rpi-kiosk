import os
import sys

os.environ.setdefault("DISPLAY", ":0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PyQt5.QtWidgets import QDialog, QPushButton

from ui.widgets.quit_modal import QuitModal
from ui.header import HeaderWidget


class TestQuitModal:
    def test_instantiation(self, qtbot):
        modal = QuitModal(parent=None)
        qtbot.addWidget(modal)
        assert modal is not None

    def test_cancel_rejects(self, qtbot):
        modal = QuitModal(parent=None)
        qtbot.addWidget(modal)
        cancel = next(
            b for b in modal.findChildren(QPushButton) if b.text() == "Cancel"
        )
        cancel.clicked.emit()
        assert modal.result() == QDialog.Rejected

    def test_quit_accepts(self, qtbot):
        modal = QuitModal(parent=None)
        qtbot.addWidget(modal)
        quit_btn = next(
            b for b in modal.findChildren(QPushButton) if b.text() == "Quit"
        )
        quit_btn.clicked.emit()
        assert modal.result() == QDialog.Accepted


class TestHeaderQuitButton:
    def test_quit_button_present(self, qtbot):
        header = HeaderWidget()
        qtbot.addWidget(header)
        assert header._quit_btn is not None

    def test_quit_button_emits_signal(self, qtbot):
        header = HeaderWidget()
        qtbot.addWidget(header)
        received = []
        header.quit_requested.connect(lambda: received.append(True))
        header._quit_btn.clicked.emit()
        assert received == [True]
