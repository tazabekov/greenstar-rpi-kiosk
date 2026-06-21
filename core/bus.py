from PyQt5.QtCore import QObject, pyqtSignal


class AppBus(QObject):
    transaction_added   = pyqtSignal(object)           # Transaction
    transaction_event   = pyqtSignal(str, object)      # tx_id, TransactionEvent
    payment_requested   = pyqtSignal(str, float, str)  # tx_id, amount, payment_type
    payment_result      = pyqtSignal(str, bool, str)   # tx_id, success, message
    settings_changed    = pyqtSignal(str, str, str)    # name, location, kiosk_id


bus = AppBus()
