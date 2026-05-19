"""
Definición de Eventos de Dominio - Servicio de Pedidos
=======================================================
En Event Sourcing, los eventos son la fuente de verdad.
Son inmutables, representan HECHOS que ya ocurrieron.

Convención de nombres: pasado (OrderPlaced, OrderConfirmed, etc.)
"""

from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DomainEvent(BaseModel):
    """Clase base para todos los eventos de dominio"""
    event_type: str = ""
    occurred_at: str = Field(default_factory=_now)


class OrderPlaced(DomainEvent):
    """Evento: se creó un nuevo pedido"""
    event_type: str = "OrderPlaced"
    order_id: str
    customer_id: str
    # Los datos del item se DESNORMALIZAN en el evento (nombre, precio)
    # porque el evento debe ser auto-contenido e inmutable en el tiempo
    items: List[Dict[str, Any]]
    total: float


class OrderConfirmed(DomainEvent):
    """Evento: el pedido fue confirmado (stock reservado exitosamente)"""
    event_type: str = "OrderConfirmed"
    order_id: str


class OrderCancelled(DomainEvent):
    """Evento: el pedido fue cancelado"""
    event_type: str = "OrderCancelled"
    order_id: str
    reason: str = ""
    items: List[Dict] = []


class OrderShipped(DomainEvent):
    """Evento: el pedido fue enviado"""
    event_type: str = "OrderShipped"
    order_id: str
    tracking_number: str
    items: List[Dict] = []


def build_order_state(events: List[Dict]) -> Dict[str, Any]:
    """
    Reconstruye el estado actual de un pedido reproduciendo todos sus eventos.

    CONCEPTO CLAVE del Event Sourcing:
    El estado no se almacena directamente. Se DERIVA aplicando
    cada evento en orden cronológico. Esto permite:
    - Auditoría completa (ver qué pasó y cuándo)
    - Time travel (¿cómo era el estado en t-3?)
    - Corrección de proyecciones sin perder datos

    Args:
        events: Lista de registros de eventos desde el event store
                Cada registro tiene: event_type, payload, version, occurred_at

    Returns:
        Estado actual del pedido como diccionario
    """
    state: Dict[str, Any] = {}

    for record in events:
        # Los eventos vienen de la BD con el payload en record["payload"]
        if "payload" in record:
            payload = record["payload"]
            event_type = record["event_type"]
        else:
            payload = record
            event_type = record.get("event_type", "")

        if event_type == "OrderPlaced":
            state = {
                "id": payload["order_id"],
                "customer_id": payload["customer_id"],
                "items": payload["items"],
                "total": payload["total"],
                "status": "PENDING",
                "created_at": payload["occurred_at"],
                "updated_at": payload["occurred_at"],
            }

        elif event_type == "OrderConfirmed":
            state["status"] = "CONFIRMED"
            state["updated_at"] = payload["occurred_at"]

        elif event_type == "OrderCancelled":
            state["status"] = "CANCELLED"
            state["cancellation_reason"] = payload.get("reason", "")
            state["updated_at"] = payload["occurred_at"]

        elif event_type == "OrderShipped":
            state["status"] = "SHIPPED"
            state["tracking_number"] = payload.get("tracking_number")
            state["updated_at"] = payload["occurred_at"]

    return state
