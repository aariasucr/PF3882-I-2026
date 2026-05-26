"""
Esquemas de eventos compartidos para el ejemplo del patrón Saga.
Todos los eventos son modelos Pydantic inmutables que se pasan entre servicios.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field
import uuid


def new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class BaseEvent(BaseModel):
    event_id: str = Field(default_factory=new_id)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Eventos de pedidos
# ---------------------------------------------------------------------------

class OrderItem(BaseModel):
    sku: str
    quantity: int
    unit_price: float


class OrderCreatedEvent(BaseEvent):
    event_type: str = "order_created"
    order_id: str
    customer_id: str
    items: List[OrderItem]
    total_amount: float


class OrderConfirmedEvent(BaseEvent):
    event_type: str = "order_confirmed"
    order_id: str


class OrderCancelledEvent(BaseEvent):
    event_type: str = "order_cancelled"
    order_id: str
    reason: str


# ---------------------------------------------------------------------------
# Eventos de pagos
# ---------------------------------------------------------------------------

class PaymentCompletedEvent(BaseEvent):
    event_type: str = "payment_completed"
    order_id: str
    payment_id: str
    amount: float


class PaymentFailedEvent(BaseEvent):
    event_type: str = "payment_failed"
    order_id: str
    reason: str


class PaymentRefundedEvent(BaseEvent):
    event_type: str = "payment_refunded"
    order_id: str
    payment_id: str


# ---------------------------------------------------------------------------
# Eventos de inventario
# ---------------------------------------------------------------------------

class StockReservedEvent(BaseEvent):
    event_type: str = "stock_reserved"
    order_id: str
    reservation_id: str


class StockUnavailableEvent(BaseEvent):
    event_type: str = "stock_unavailable"
    order_id: str
    reason: str


class StockReleasedEvent(BaseEvent):
    event_type: str = "stock_released"
    order_id: str
    reservation_id: str
