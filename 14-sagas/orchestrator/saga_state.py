"""
Máquina de estados de la Saga para el estilo Orquestación.

El orquestador mantiene una SagaInstance por pedido y la avanza paso a
paso. Si algún paso falla, el orquestador ejecuta los pasos de compensación
en orden inverso.

Diagrama de estados
-------------------
    STARTED
      │
      ▼
    ORDER_CREATED ──(fallo)──► CANCELLING_ORDER ──► FAILED
      │
      ▼
    PAYMENT_PROCESSED ──(fallo)──► CANCELLING_ORDER ──► FAILED
      │
      ▼
    STOCK_RESERVED ──(fallo)──► REFUNDING_PAYMENT ──► CANCELLING_ORDER ──► FAILED
      │
      ▼
    COMPLETED
"""

from __future__ import annotations
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime, timezone
import uuid


class SagaStep(str, Enum):
    STARTED = "STARTED"
    ORDER_CREATED = "ORDER_CREATED"
    PAYMENT_PROCESSED = "PAYMENT_PROCESSED"
    STOCK_RESERVED = "STOCK_RESERVED"
    COMPLETED = "COMPLETED"
    # Pasos de compensación
    REFUNDING_PAYMENT = "REFUNDING_PAYMENT"
    CANCELLING_ORDER = "CANCELLING_ORDER"
    FAILED = "FAILED"


class SagaInstance:
    """Guarda el estado mutable de una ejecución de saga."""

    def __init__(self, saga_id: str, order_id: str, customer_id: str,
                 items: list, total_amount: float) -> None:
        self.saga_id = saga_id
        self.order_id = order_id
        self.customer_id = customer_id
        self.items = items
        self.total_amount = total_amount

        self.step: SagaStep = SagaStep.STARTED
        self.payment_id: Optional[str] = None
        self.reservation_id: Optional[str] = None
        self.failure_reason: Optional[str] = None

        self.history: List[dict] = []
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Transiciones
    # ------------------------------------------------------------------

    def transition(self, new_step: SagaStep, note: str = "") -> None:
        self.history.append({
            "from": self.step,
            "to": new_step,
            "note": note,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        self.step = new_step
        self.updated_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Serialización (para la API REST)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "saga_id": self.saga_id,
            "order_id": self.order_id,
            "customer_id": self.customer_id,
            "total_amount": self.total_amount,
            "step": self.step,
            "payment_id": self.payment_id,
            "reservation_id": self.reservation_id,
            "failure_reason": self.failure_reason,
            "history": self.history,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# Registro global  {saga_id: SagaInstance}
saga_registry: Dict[str, SagaInstance] = {}
