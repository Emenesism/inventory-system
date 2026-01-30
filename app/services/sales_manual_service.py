from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SalesManualLine:
    product_name: str
    quantity: int
    price: float = 0.0
