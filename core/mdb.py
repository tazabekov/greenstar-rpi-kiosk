"""
MDB Pi Hat integration — hardware arriving ~2026-06-23.

Reads vend events from the USB serial port exposed by the MDB Pi Hat
(https://docs.qibixx.com/mdb-products/mdb-pi-hat).

Interface (to be implemented):
    class MdbReader(QObject):
        vend_event = pyqtSignal(str, float)  # item_name, price

    On each completed vend, create a Transaction and emit bus.transaction_added(tx).

USB device will appear as /dev/ttyUSB0 or /dev/ttyACM0.
Baud rate and protocol per qibixx documentation.
"""
