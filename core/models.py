from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Transaction:
    time: datetime
    item: str
    amount: float
    payment_type: str   # "fiat" | "bitcoin"
    status: str = "completed"  # "pending" | "completed" | "failed"
