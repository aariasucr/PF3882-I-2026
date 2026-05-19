"""
Servicio de Pedidos — Event Sourcing con Redis Streams
=======================================================

Mismo dominio que la versión RabbitMQ, diferente mecanismo de mensajería.

Diferencias clave vs. RabbitMQ:
  - Se publica al STREAM (stream:orders) en lugar de routing_key
  - El handler filtra por payload["event_type"] en lugar de routing_key
  - El consumer group permite que múltiples servicios lean el mismo stream
  - Los mensajes del stream son persistentes (se puede hacer "replay")

Flujo:
  POST /orders → OrderPlaced → XADD stream:orders
  inventory-cg lee stream:orders → reserva stock → XADD stream:inventory
  orders-cg   lee stream:inventory → confirma/cancela pedido
  notifications-cg lee ambos streams → registra notificaciones
"""

import uuid
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import database
import events as evt
import broker

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


# ─── Modelos de entrada ───────────────────────────────────────────────────────

class OrderItem(BaseModel):
    product_id:   str
    product_name: str
    quantity:     int
    unit_price:   float


class PlaceOrderRequest(BaseModel):
    customer_id: str
    items:       List[OrderItem]


class ShipOrderRequest(BaseModel):
    tracking_number: str


# ─── Saga Handler ─────────────────────────────────────────────────────────────

async def handle_inventory_event(payload: dict, stream: str):
    """
    Reacciona a eventos del stream de inventario.

    A diferencia de RabbitMQ (donde el routing_key dice qué pasó),
    aquí miramos payload["event_type"] para saber qué evento llegó.
    """
    event_type = payload.get("event_type")
    order_id   = payload.get("order_id")

    if not order_id or event_type not in ("StockReserved", "StockInsufficient"):
        return

    stored_events = await database.get_events(order_id)
    if not stored_events:
        return

    state = evt.build_order_state(stored_events)
    if state.get("status") != "PENDING":
        return

    version = len(stored_events) + 1

    if event_type == "StockReserved":
        event = evt.OrderConfirmed(order_id=order_id)
        await database.save_event(
            order_id, "Order", event.event_type, event.model_dump(), version
        )
        await broker.publish(broker.STREAM_ORDERS, event.model_dump())

        new_events = await database.get_events(order_id)
        await database.upsert_order_projection(evt.build_order_state(new_events))
        log.info("✅ Pedido %s CONFIRMADO (Redis)", order_id)

    elif event_type == "StockInsufficient":
        reason = payload.get("reason", "Stock insuficiente")
        event  = evt.OrderCancelled(order_id=order_id, reason=reason, items=state.get("items", []))
        await database.save_event(
            order_id, "Order", event.event_type, event.model_dump(), version
        )
        await broker.publish(broker.STREAM_ORDERS, event.model_dump())

        new_events = await database.get_events(order_id)
        await database.upsert_order_projection(evt.build_order_state(new_events))
        log.warning("❌ Pedido %s CANCELADO: %s (Redis)", order_id, reason)


# ─── Ciclo de vida ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    await broker.connect()

    # Leer respuestas de inventario desde stream:inventory
    asyncio.create_task(
        broker.consume(
            stream=broker.STREAM_INVENTORY,
            group="orders-cg",
            consumer="orders-1",
            handler=handle_inventory_event,
        )
    )

    yield

    await broker.disconnect()
    await database.close_db()


app = FastAPI(
    title="Orders Service",
    description="Microservicio de pedidos con Event Sourcing + Redis Streams",
    lifespan=lifespan,
)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/orders", status_code=201)
async def place_order(request: PlaceOrderRequest):
    order_id = str(uuid.uuid4())
    total    = round(sum(i.quantity * i.unit_price for i in request.items), 2)
    items    = [i.model_dump() for i in request.items]

    event = evt.OrderPlaced(
        order_id=order_id,
        customer_id=request.customer_id,
        items=items,
        total=total,
    )

    await database.save_event(
        order_id, "Order", event.event_type, event.model_dump(), version=1
    )

    state = evt.build_order_state(
        [{"event_type": event.event_type, "payload": event.model_dump()}]
    )
    await database.upsert_order_projection(state)

    # Publicar al stream de orders (Redis XADD)
    await broker.publish(broker.STREAM_ORDERS, event.model_dump())

    return {
        "message": "Pedido recibido. Verificando inventario...",
        "order_id": order_id,
        "status": "PENDING",
        "total": total,
    }


@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    stored_events = await database.get_events(order_id)
    if not stored_events:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return evt.build_order_state(stored_events)


@app.get("/orders/{order_id}/history")
async def get_order_history(order_id: str):
    stored_events = await database.get_events(order_id)
    if not stored_events:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    return {
        "order_id":      order_id,
        "total_events":  len(stored_events),
        "current_state": evt.build_order_state(stored_events),
        "events": [
            {
                "version":     e["version"],
                "event_type":  e["event_type"],
                "occurred_at": e["occurred_at"].isoformat(),
                "payload":     e["payload"],
            }
            for e in stored_events
        ],
    }


@app.get("/orders")
async def list_orders():
    orders = await database.get_all_orders()
    return {"total": len(orders), "orders": orders}


@app.post("/orders/{order_id}/ship")
async def ship_order(order_id: str, request: ShipOrderRequest):
    stored_events = await database.get_events(order_id)
    if not stored_events:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    state = evt.build_order_state(stored_events)
    if state.get("status") != "CONFIRMED":
        raise HTTPException(
            status_code=400,
            detail=f"Solo se pueden enviar pedidos CONFIRMADOS. Estado: {state.get('status')}",
        )

    version = len(stored_events) + 1
    event   = evt.OrderShipped(order_id=order_id, tracking_number=request.tracking_number, items=state.get("items", []))

    await database.save_event(
        order_id, "Order", event.event_type, event.model_dump(), version
    )
    await broker.publish(broker.STREAM_ORDERS, event.model_dump())

    new_events = await database.get_events(order_id)
    new_state  = evt.build_order_state(new_events)
    await database.upsert_order_projection(new_state)
    return new_state


@app.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str):
    stored_events = await database.get_events(order_id)
    if not stored_events:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    state = evt.build_order_state(stored_events)
    if state.get("status") not in ("PENDING", "CONFIRMED"):
        raise HTTPException(
            status_code=400,
            detail=f"No se puede cancelar un pedido en estado {state.get('status')}",
        )

    version = len(stored_events) + 1
    event   = evt.OrderCancelled(order_id=order_id, reason="Cancelado por el cliente", items=state.get("items", []))

    await database.save_event(
        order_id, "Order", event.event_type, event.model_dump(), version
    )
    await broker.publish(broker.STREAM_ORDERS, event.model_dump())

    new_events = await database.get_events(order_id)
    new_state  = evt.build_order_state(new_events)
    await database.upsert_order_projection(new_state)
    return new_state


@app.get("/health")
async def health():
    return {"status": "ok", "service": "orders", "broker": "redis-streams"}
