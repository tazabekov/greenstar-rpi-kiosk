"""
MDB Pi Hat integration — cashless peripheral mode.

The Pi Hat emulates a cashless peripheral (MDB address 0x10).
KreaTouch acts as the VMC master and sends VEND requests when a customer
selects a product. This reader approves or denies each vend based on the
Square / crypto payment result.

Hardware connection:
  KreaTouch MDB cable  →  Right (Peripheral) port on Pi Hat
  Jumper Set 1: REMOVED  (Split Mode — not horizontal/sniff)
  Pi Hat USB  →  RPi5   → /dev/ttyACM0   (USB mode; close USB Toggle Jumper)
      or UART GPIO       → /dev/ttyS0    (UART mode on Pi 5)

Serial protocol: 115200 8N1, plain text, each command/response terminated \\n.

Vend flow:
  KreaTouch sends VEND request → hat notifies us: c,STATUS,VEND,<amount>,<item>
  We create Transaction → emit bus.transaction_added + bus.payment_requested
  Square/crypto resolves → bus.payment_result fires
  We send C,VEND,<amount> (approve) or C,STOP (deny) back to the hat
  Hat tells KreaTouch to dispense (or cancel)
"""

import logging
import os
import threading
from datetime import datetime

from PyQt5.QtCore import QThread, pyqtSignal

from core.bus import bus
from core.models import Transaction, TransactionEvent

log = logging.getLogger(__name__)

_BAUD = 115200
# Auto-detect order: USB CDC first (most common), then UART
_AUTO_PORTS = ["/dev/ttyACM0", "/dev/ttyUSB0", "/dev/ttyS0"]


def _resolve_port() -> str | None:
    explicit = os.environ.get("GKM_MDB_PORT", "").strip()
    if explicit:
        return explicit
    for p in _AUTO_PORTS:
        if os.path.exists(p):
            return p
    return None


class MdbReader(QThread):
    """
    Background thread that owns the serial connection to the MDB Pi Hat.

    Signals:
        mdb_ok_changed(bool) — True when hat is enabled and talking to VMC;
                               False on open failure, read error, or INACTIVE status.
    """

    mdb_ok_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._port = _resolve_port()
        self._ser = None
        self._write_lock = threading.Lock()
        self._running = False
        # tx_id → amount waiting for payment resolution
        self._pending: dict[str, float] = {}
        bus.payment_result.connect(self._on_payment_result)

    # ── QThread entry point ───────────────────────────────────────────────

    def run(self):
        if not self._port:
            log.warning("MDB: no port found — set GKM_MDB_PORT or connect the Pi Hat")
            self.mdb_ok_changed.emit(False)
            return

        try:
            import serial
            self._ser = serial.Serial(self._port, _BAUD, timeout=1)
        except Exception as exc:
            log.error("MDB: cannot open %s: %s", self._port, exc)
            self.mdb_ok_changed.emit(False)
            return

        log.info("MDB: opened %s at %d baud", self._port, _BAUD)
        self._running = True
        self._configure()

        while self._running:
            try:
                raw = self._ser.readline()
            except Exception as exc:
                log.error("MDB: read error: %s", exc)
                self.mdb_ok_changed.emit(False)
                break

            line = raw.decode("ascii", errors="replace").strip()
            if line:
                log.debug("MDB << %s", line)
                self._handle(line)

        self._send("C,0")  # disable peripheral before closing
        if self._ser and self._ser.is_open:
            self._ser.close()
        log.info("MDB: reader stopped")

    def stop(self):
        self._running = False
        self.wait(3000)

    # ── private: serial I/O ───────────────────────────────────────────────

    def _send(self, cmd: str):
        if not (self._ser and self._ser.is_open):
            return
        with self._write_lock:
            try:
                log.debug("MDB >> %s", cmd)
                self._ser.write((cmd + "\n").encode())
            except Exception as exc:
                log.error("MDB: write error: %s", exc)

    def _configure(self):
        self._send("C,SETCONF,mdb-addr=0x10")  # standard cashless device address
        self._send("C,1")                        # enable as cashless peripheral

    # ── private: protocol handler ─────────────────────────────────────────

    def _handle(self, line: str):
        if line == "c,STATUS,ENABLED":
            log.info("MDB: peripheral enabled — waiting for vend requests")
            self.mdb_ok_changed.emit(True)

        elif line == "c,STATUS,INACTIVE":
            log.warning("MDB: INACTIVE — hat is not talking to VMC")
            self.mdb_ok_changed.emit(False)

        elif line.startswith("c,STATUS,VEND,"):
            # c,STATUS,VEND,<amount>,<product_id>
            parts = line.split(",")
            if len(parts) < 5:
                log.warning("MDB: malformed VEND line: %s", line)
                return
            try:
                amount = float(parts[3])
            except ValueError:
                log.warning("MDB: bad amount in: %s", line)
                return
            self._on_vend_request(amount, product_id=parts[4], raw=line)

        elif line == "c,VEND,SUCCESS":
            log.info("MDB: vend dispensed OK")

        elif line.startswith("c,ERR"):
            log.warning("MDB: error from hat: %s", line)
            self._send("C,STOP")  # cancel any in-flight vend on hardware error

    def _on_vend_request(self, amount: float, product_id: str, raw: str):
        payment_type = "bitcoin" if bus.crypto_mode else "fiat"
        now = datetime.now()
        tx = Transaction(
            time=now,
            item=f"Item {product_id}",
            amount=amount,
            payment_type=payment_type,
        )
        tx.events.append(TransactionEvent(
            timestamp=now,
            source="MDB",
            direction="in",
            message=f"VEND REQUEST  ${amount:.2f}  item={product_id}",
            raw=raw,
        ))
        self._pending[tx.tx_id] = amount
        bus.transaction_added.emit(tx)
        bus.payment_requested.emit(tx.tx_id, amount, payment_type)
        log.info("MDB: vend $%.2f item=%s tx=%s type=%s",
                 amount, product_id, tx.tx_id, payment_type)

    def _on_payment_result(self, tx_id: str, success: bool, message: str):
        amount = self._pending.pop(tx_id, None)
        if amount is None:
            return  # not an MDB-originated transaction
        if success:
            self._send(f"C,VEND,{amount:.2f}")
            log.info("MDB: approved $%.2f tx=%s", amount, tx_id)
        else:
            self._send("C,STOP")
            log.info("MDB: denied tx=%s: %s", tx_id, message)


def make_mdb_reader(parent=None) -> "MdbReader | None":
    """Returns MdbReader when a port is available, else None (no-op)."""
    if not _resolve_port():
        log.info("MDB: no serial port available — reader disabled")
        return None
    return MdbReader(parent)
