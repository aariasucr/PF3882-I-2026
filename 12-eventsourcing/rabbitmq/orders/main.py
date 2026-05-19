"""
Servicio de Pedidos — Event Sourcing con RabbitMQ
==================================================

Flujo completo (Saga Coreografiada):
  1. Cliente → POST /orders       → guarda OrderPlaced    → publica orders.placed
  2. Inventario recibe orders.placed → reserva stock
     2a. Éxito  → publica inventory.stock_reserved
     2b. Error  → publica inventory.stock_insufficient
  3. Este servicio recibe inventory.*:
     3a. stock_reserved     → guarda OrderConfirmed → publica orders.confirmed
     3b. stock_insufficient → guarda OrderCancelled → publica orders.cancelled
  4. Notificaciones escucha todo y registra cada evento

Conceptos que demuestra:
  - Event Store (append-only)
  - Reconstrucción de estado desde eventos
  - CQRS (lectura desde proyección, escritura en event store)
  - Saga coreografiada (sin orquestador central)
  - Consistencia eventual
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


# ─── Modelos de entrada (Comandos) ────────────────────────────────────────────

class OrderItem(BaseModel):
    product_id:   str
    product_name: str   # desnormalizado: captura el nombre al momento del pedido
    quantity:     int
    unit_price:   float  # desnormalizado: captura el precio al momento del pedido


class PlaceOrderRequest(BaseModel):
    customer_id: str
    items:       List[OrderItem]


class ShipOrderRequest(BaseModel):
    tracking_number: str


# ─── Saga Handler: reacciona a eventos de inventario ─────────────────────────

async def handle_inventory_event(payload: dict, routing_key: str):
    """
    Implementa el lado 'orders' de la Saga de pedido.

    No hay orquestador central: cada servicio reacciona a eventos
    y publica nuevos eventos. Esto es una Saga COREOGRAFIADA.
    """
    order_id = payload.get("order_id")
    if not order_id:
        return

    stored_events = await database.get_events(order_id)
    if not stored_events:
        return

    state = evt.build_order_state(stored_events)

    # Solo procesamos pedidos que están esperando confirmación
    if state.get("status") != "PENDING":
        return

    version = len(stored_events) + 1

    if routing_key == "inventory.stock_reserved":
        event = evt.OrderConfirmed(order_id=order_id)
        await database.save_event(
            order_id, "Order", event.event_type, event.model_dump(), version
        )
        await broker.publish("orders.confirmed", event.model_dump())

        new_events = await database.get_events(order_id)
        new_state  = evt.build_order_state(new_events)
        await database.upsert_order_projection(new_state)
        log.info("✅ Pedido %s CONFIRMADO", order_id)

    elif routing_key == "inventory.stock_insufficient":
        reason = payload.get("reason", "Stock insuficiente")
        event  = evt.OrderCancelled(order_id=order_id, reason=reason, items=state.get("items", []))
        await database.save_event(
            order_id, "Order", event.event_type, event.model_dump(), version
        )
        await broker.publish("orders.cancelled", event.model_dump())

        new_events = await database.get_events(order_id)
        new_state  = evt.build_order_state(new_events)
        await database.upsert_order_projection(new_state)
        log.warning("❌ Pedido %s CANCELADO: %s", order_id, reason)


# ─── Ciclo de vida ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    await broker.connect()

    # Iniciar consumidor en background: escucha respuestas del inventario
    asyncio.create_task(
        broker.consume(
            queue_name="orders.inventory_responses",
            routing_keys=["inventory.stock_reserved", "inventory.stock_insufficient"],
            handler=handle_inventory_event,
        )
    )

    yield

    await broker.disconnect()
    await database.close_db()


app = FastAPI(
    title="Orders Service",
    description="Microservicio de pedidos con Event Sourcing + RabbitMQ",
    lifespan=lifespan,
)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/orders", status_code=201)
async def place_order(request: PlaceOrderRequest):
    """
    Comando: Crear un nuevo pedido.

    El cliente llama aquí y recibe respuesta inmediata (PENDING).
    La confirmación llegará de forma asíncrona cuando el inventario responda.
    Esto es CONSISTENCIA EVENTUAL en acción.
    """
    order_id = str(uuid.uuid4())
    total    = round(sum(i.quantity * i.unit_price for i in request.items), 2)
    items    = [i.model_dump() for i in request.items]

    event = evt.OrderPlaced(
        order_id=order_id,
        customer_id=request.customer_id,
        items=items,
        total=total,
    )

    # 1. Persistir en el event store ANTES de publicar (durabilidad primero)
    await database.save_event(
        order_id, "Order", event.event_type, event.model_dump(), version=1
    )

    # 2. Actualizar proyección para que aparezca en la lista de pedidos
    state = evt.build_order_state([{"event_type": event.event_type, "payload": event.model_dump()}])
    await database.upsert_order_projection(state)

    # 3. Publicar al broker → inventario reaccionará de forma asíncrona
    await broker.publish("orders.placed", event.model_dump())

    return {
        "message": "Pedido recibido. Verificando inventario...",
        "order_id": order_id,
        "status": "PENDING",
        "total": total,
    }


@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    """
    Consulta: Estado actual del pedido.

    CLAVE: El estado se RECONSTRUYE reproduciendo todos los eventos.
    No hay una columna 'status' que se actualice con UPDATE.
    Pruébalo: el historial en /history muestra cómo llegamos aquí.
    """
    stored_events = await database.get_events(order_id)
    if not stored_events:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    # ← Aquí está la esencia del Event Sourcing
    return evt.build_order_state(stored_events)


@app.get("/orders/{order_id}/history")
async def get_order_history(order_id: str):
    """
    Consulta: Historial completo de eventos del pedido.

    Con Event Sourcing tienes un audit trail GRATUITO.
    Puedes responder: ¿qué pasó exactamente?, ¿cuándo?, ¿en qué orden?
    Esto es IMPOSIBLE con CRUD tradicional (UPDATE sobreescribe el pasado).
    """
    stored_events = await database.get_events(order_id)
    if not stored_events:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    return {
        "order_id":     order_id,
        "total_events": len(stored_events),
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
    """Lista todos los pedidos (desde proyección CQRS, no desde event store)"""
    orders = await database.get_all_orders()
    return {"total": len(orders), "orders": orders}


@app.post("/orders/{order_id}/ship")
async def ship_order(order_id: str, request: ShipOrderRequest):
    """Comando: Marcar un pedido confirmado como enviado"""
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
    await broker.publish("orders.shipped", event.model_dump())

    new_events = await database.get_events(order_id)
    new_state  = evt.build_order_state(new_events)
    await database.upsert_order_projection(new_state)

    return new_state


@app.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str):
    """Comando: Cancelar un pedido (solo PENDING o CONFIRMED)"""
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
    await broker.publish("orders.cancelled", event.model_dump())

    new_events = await database.get_events(order_id)
    new_state  = evt.build_order_state(new_events)
    await database.upsert_order_projection(new_state)

    return new_state


@app.get("/health")
async def health():
    return {"status": "ok", "service": "orders", "broker": "rabbitmq"}
