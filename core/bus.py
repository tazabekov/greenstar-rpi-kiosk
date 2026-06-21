from PyQt5.QtCore import QObject, pyqtSignal


class AppBus(QObject):
    transaction_added = pyqtSignal(object)      # Transaction
    payment_requested = pyqtSignal(float, str)  # amount, type ("fiat"|"bitcoin")
    payment_result    = pyqtSignal(bool, str)   # success, message


bus = AppBus()
