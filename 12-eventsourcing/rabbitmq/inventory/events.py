"""
Definición de Eventos de Dominio - Servicio de Inventario
==========================================================
El stock no es un número almacenado: es la SUMA de movimientos.
Cada reserva, liberación o ajuste es un evento inmutable.
"""

from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DomainEvent(BaseModel):
    event_type: str = ""
    occurred_at: str = Field(default_factory=_now)


class ProductCreated(DomainEvent):
    """Evento: se registró un nuevo producto en el inventario"""
    event_type: str = "ProductCreated"
    product_id: str
    name: str
    price: float
    initial_stock: int


class StockAdded(DomainEvent):
    """Evento: se añadió stock al inventario (reposición)"""
    event_type: str = "StockAdded"
    product_id: str
    quantity: int
    reason: str = "Reposición"


class StockReserved(DomainEvent):
    """Evento: se reservó stock para un pedido"""
    event_type: str = "StockReserved"
    order_id: str
    product_id: str
    quantity: int


class StockInsufficient(DomainEvent):
    """Evento: no había suficiente stock para satisfacer el pedido"""
    event_type: str = "StockInsufficient"
    order_id: str
    product_id: str
    requested: int
    available: int
    reason: str = "Stock insuficiente"


class StockReleased(DomainEvent):
    """Evento: se liberó stock reservado (pedido cancelado)"""
    event_type: str = "StockReleased"
    order_id: str
    product_id: str
    quantity: int
    reason: str = "Pedido cancelado"


class StockShipped(DomainEvent):
    """Evento: el stock reservado fue despachado (pedido enviado)"""
    event_type: str = "StockShipped"
    order_id: str
    product_id: str
    quantity: int


def build_product_state(events: List[Dict]) -> Dict[str, Any]:
    """
    Reconstruye el estado del producto (stock) reproduciendo todos sus eventos.

    CONCEPTO CLAVE:
    El stock disponible no es un número guardado en una columna.
    Es el resultado de SUMAR y RESTAR cada movimiento registrado.
    Igual que un estado de cuenta bancaria: el saldo = suma de transacciones.
    """
    state: Dict[str, Any] = {}

    for record in events:
        if "payload" in record:
            payload = record["payload"]
            event_type = record["event_type"]
        else:
            payload = record
            event_type = record.get("event_type", "")

        if event_type == "ProductCreated":
            state = {
                "id": payload["product_id"],
                "name": payload["name"],
                "price": payload["price"],
                "total_stock": payload["initial_stock"],
                "reserved_stock": 0,
                "created_at": payload["occurred_at"],
                "updated_at": payload["occurred_at"],
            }

        elif event_type == "StockAdded":
            state["total_stock"] = state.get("total_stock", 0) + payload["quantity"]
            state["updated_at"] = payload["occurred_at"]

        elif event_type == "StockReserved":
            state["reserved_stock"] = state.get("reserved_stock", 0) + payload["quantity"]
            state["updated_at"] = payload["occurred_at"]

        elif event_type == "StockReleased":
            state["reserved_stock"] = max(
                0, state.get("reserved_stock", 0) - payload["quantity"]
            )
            state["updated_at"] = payload["occurred_at"]

        elif event_type == "StockShipped":
            qty = payload["quantity"]
            state["reserved_stock"] = max(0, state.get("reserved_stock", 0) - qty)
            state["total_stock"]    = max(0, state.get("total_stock", 0) - qty)
            state["updated_at"]     = payload["occurred_at"]

    if state:
        state["available_stock"] = state["total_stock"] - state["reserved_stock"]

    return state
