import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class TransactionEvent:
    timestamp: datetime
    source: str      # "MDB" | "SQUARE" | "SYSTEM"
    direction: str   # "in" | "out"
    message: str
    raw: str = ""    # raw bytes / JSON for debugging


@dataclass
class Transaction:
    time: datetime
    item: str
    amount: float
    payment_type: str        # "fiat" | "bitcoin"
    status: str = "pending"  # "pending" | "completed" | "failed"
    tx_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    events: List[TransactionEvent] = field(default_factory=list)
