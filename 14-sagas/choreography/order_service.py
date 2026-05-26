"""
Servicio de Pedidos — Estilo Coreografía
Puerto: 8001

Responsabilidades
-----------------
* Aceptar nuevos pedidos del cliente  →  publica OrderCreatedEvent
* Escuchar payment_failed             →  compensar cancelando el pedido
* Escuchar stock_unavailable          →  compensar cancelando el pedido
* Escuchar stock_reserved             →  confirmar el pedido

Máquina de estados:  PENDING → CONFIRMED
                              ↘ CANCELLED  (compensación)
"""

from __future__ import annotations
from shared.event_bus import bus
from shared.events import (
    OrderItem, OrderCreatedEvent, OrderConfirmedEvent, OrderCancelledEvent,
    PaymentFailedEvent, StockReservedEvent, StockUnavailableEvent,
)
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from typing import Dict, List
import logging
import uuid
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [PEDIDOS] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Servicio de Pedidos (Coreografía)", version="1.0")

# ---------------------------------------------------------------------------
# Almacén en memoria  {order_id: registro_pedido}
# ---------------------------------------------------------------------------
orders: Dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Modelos de API
# ---------------------------------------------------------------------------

class CreateOrderRequest(BaseModel):
    customer_id: str
    items: List[OrderItem]


# ---------------------------------------------------------------------------
# Endpoints REST
# ---------------------------------------------------------------------------

@app.post("/orders", status_code=201)
async def create_order(req: CreateOrderRequest):
    """Crea un nuevo pedido y publica OrderCreatedEvent."""
    order_id = str(uuid.uuid4())
    total = sum(i.unit_price * i.quantity for i in req.items)

    order = {
        "order_id": order_id,
        "customer_id": req.customer_id,
        "items": [i.model_dump() for i in req.items],
        "total_amount": total,
        "status": "PENDING",
    }
    orders[order_id] = order
    logger.info("Pedido %s creado (total=%.2f)", order_id, total)

    event = OrderCreatedEvent(
        order_id=order_id,
        customer_id=req.customer_id,
        items=req.items,
        total_amount=total,
    )
    await bus.publish("order_created", event)
    return order


@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    """Devuelve el estado actual del pedido."""
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return orders[order_id]


@app.get("/orders")
async def list_orders():
    return list(orders.values())


# ---------------------------------------------------------------------------
# Handlers de eventos  (suscritos al inicio)
# ---------------------------------------------------------------------------

@bus.subscribe("payment_failed")
async def on_payment_failed(event: PaymentFailedEvent):
    """Transacción compensatoria: cancela el pedido cuando el pago falla."""
    order = orders.get(event.order_id)
    if not order:
        return
    order["status"] = "CANCELLED"
    order["cancel_reason"] = event.reason
    logger.info("Pedido %s CANCELADO — pago fallido: %s",
                event.order_id, event.reason)

    cancel_event = OrderCancelledEvent(
        order_id=event.order_id,
        reason=f"Pago fallido: {event.reason}",
    )
    await bus.publish("order_cancelled", cancel_event)


@bus.subscribe("stock_unavailable")
async def on_stock_unavailable(event: StockUnavailableEvent):
    """Transacción compensatoria: cancela el pedido cuando el stock no está disponible."""
    order = orders.get(event.order_id)
    if not order:
        return
    order["status"] = "CANCELLED"
    order["cancel_reason"] = event.reason
    logger.info("Pedido %s CANCELADO — stock no disponible: %s",
                event.order_id, event.reason)

    cancel_event = OrderCancelledEvent(
        order_id=event.order_id,
        reason=f"Stock no disponible: {event.reason}",
    )
    await bus.publish("order_cancelled", cancel_event)


@bus.subscribe("stock_reserved")
async def on_stock_reserved(event: StockReservedEvent):
    """Camino exitoso: confirma el pedido cuando el stock se reserva con éxito."""
    order = orders.get(event.order_id)
    if not order:
        return
    order["status"] = "CONFIRMED"
    order["reservation_id"] = event.reservation_id
    logger.info("Pedido %s CONFIRMADO", event.order_id)

    await bus.publish(
        "order_confirmed",
        OrderConfirmedEvent(order_id=event.order_id),
    )


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
