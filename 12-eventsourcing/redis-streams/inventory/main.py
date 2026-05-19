"""
Servicio de Inventario — Event Sourcing con Redis Streams
==========================================================

Lee stream:orders para detectar OrderPlaced y OrderCancelled.
Publica al stream:inventory los resultados (StockReserved, etc.).

La diferencia vs RabbitMQ:
  - No hay routing keys; todos los eventos de orders llegan al mismo stream
  - Filtramos por event_type en el payload
  - Los mensajes quedan en el stream: se puede hacer replay del historial
"""

import uuid
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import database
import events as evt
import broker

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class CreateProductRequest(BaseModel):
    name:          str
    price:         float
    initial_stock: int


class AddStockRequest(BaseModel):
    quantity: int
    reason:   str = "Reposición de inventario"


# ─── Saga Handler ─────────────────────────────────────────────────────────────

async def handle_order_event(payload: dict, stream: str):
    """
    Lee eventos del stream de orders y filtra por event_type.

    Todos los eventos de orders llegan aquí; solo procesamos
    OrderPlaced y OrderCancelled.
    """
    event_type = payload.get("event_type")

    if event_type == "OrderPlaced":
        await _reserve_stock(payload)
    elif event_type == "OrderCancelled":
        await _release_stock(payload)
    elif event_type == "OrderShipped":
        await _ship_stock(payload)


async def _reserve_stock(order_payload: dict):
    order_id = order_payload["order_id"]
    items    = order_payload.get("items", [])

    for item in items:
        product_id = item["product_id"]
        quantity   = item["quantity"]

        product_events = await database.get_events(product_id)

        if not product_events:
            event = evt.StockInsufficient(
                order_id=order_id,
                product_id=product_id,
                requested=quantity,
                available=0,
                reason=f"Producto '{item.get('product_name', product_id)}' no existe",
            )
            version = await database.get_next_version(order_id)
            await database.save_event(
                order_id, "Reservation", event.event_type, event.model_dump(), version
            )
            await broker.publish(broker.STREAM_INVENTORY, event.model_dump())
            return

        product_state = evt.build_product_state(product_events)
        available     = product_state.get("available_stock", 0)

        if available < quantity:
            event = evt.StockInsufficient(
                order_id=order_id,
                product_id=product_id,
                requested=quantity,
                available=available,
                reason=f"Solo hay {available} unidades de '{product_state['name']}'",
            )
            version = await database.get_next_version(order_id)
            await database.save_event(
                order_id, "Reservation", event.event_type, event.model_dump(), version
            )
            await broker.publish(broker.STREAM_INVENTORY, event.model_dump())
            log.warning("❌ Stock insuficiente para pedido %s", order_id)
            return

        next_version  = await database.get_next_version(product_id)
        reserve_event = evt.StockReserved(
            order_id=order_id, product_id=product_id, quantity=quantity
        )
        await database.save_event(
            product_id, "Product", reserve_event.event_type,
            reserve_event.model_dump(), next_version
        )

        new_events = await database.get_events(product_id)
        new_state  = evt.build_product_state(new_events)
        await database.upsert_product_projection(new_state)

        await broker.publish(broker.STREAM_INVENTORY, reserve_event.model_dump())
        log.info("✅ %d unidades de '%s' reservadas para pedido %s",
                 quantity, product_state["name"], order_id)


async def _ship_stock(order_payload: dict):
    """Descuenta el stock físico cuando el pedido es enviado"""
    order_id = order_payload["order_id"]
    items    = order_payload.get("items", [])

    for item in items:
        product_id = item["product_id"]
        quantity   = item["quantity"]

        product_events = await database.get_events(product_id)
        if not product_events:
            continue

        ship_event   = evt.StockShipped(order_id=order_id, product_id=product_id, quantity=quantity)
        next_version = await database.get_next_version(product_id)
        await database.save_event(
            product_id, "Product", ship_event.event_type,
            ship_event.model_dump(), next_version
        )

        new_events = await database.get_events(product_id)
        new_state  = evt.build_product_state(new_events)
        await database.upsert_product_projection(new_state)

        await broker.publish(broker.STREAM_INVENTORY, ship_event.model_dump())
        log.info("🚚 Despachadas %d unidades para pedido %s", quantity, order_id)


async def _release_stock(order_payload: dict):
    order_id = order_payload["order_id"]
    items    = order_payload.get("items", [])

    for item in items:
        product_id = item["product_id"]
        quantity   = item["quantity"]

        product_events = await database.get_events(product_id)
        if not product_events:
            continue

        release_event = evt.StockReleased(
            order_id=order_id,
            product_id=product_id,
            quantity=quantity,
            reason="Pedido cancelado",
        )
        next_version = await database.get_next_version(product_id)
        await database.save_event(
            product_id, "Product", release_event.event_type,
            release_event.model_dump(), next_version
        )

        new_events = await database.get_events(product_id)
        new_state  = evt.build_product_state(new_events)
        await database.upsert_product_projection(new_state)

        await broker.publish(broker.STREAM_INVENTORY, release_event.model_dump())
        log.info("🔓 %d unidades liberadas para pedido %s", quantity, order_id)


# ─── Ciclo de vida ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    await broker.connect()

    asyncio.create_task(
        broker.consume(
            stream=broker.STREAM_ORDERS,
            group="inventory-cg",
            consumer="inventory-1",
            handler=handle_order_event,
        )
    )

    yield

    await broker.disconnect()
    await database.close_db()


app = FastAPI(
    title="Inventory Service",
    description="Microservicio de inventario con Event Sourcing + Redis Streams",
    lifespan=lifespan,
)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/products", status_code=201)
async def create_product(request: CreateProductRequest):
    product_id = str(uuid.uuid4())
    event      = evt.ProductCreated(
        product_id=product_id,
        name=request.name,
        price=request.price,
        initial_stock=request.initial_stock,
    )
    await database.save_event(
        product_id, "Product", event.event_type, event.model_dump(), version=1
    )
    state = evt.build_product_state(
        [{"event_type": event.event_type, "payload": event.model_dump()}]
    )
    await database.upsert_product_projection(state)
    return {"message": "Producto creado", "product": state}


@app.post("/products/{product_id}/stock")
async def add_stock(product_id: str, request: AddStockRequest):
    product_events = await database.get_events(product_id)
    if not product_events:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    next_version = await database.get_next_version(product_id)
    event        = evt.StockAdded(
        product_id=product_id, quantity=request.quantity, reason=request.reason
    )
    await database.save_event(
        product_id, "Product", event.event_type, event.model_dump(), next_version
    )
    new_events = await database.get_events(product_id)
    state      = evt.build_product_state(new_events)
    await database.upsert_product_projection(state)
    return {"message": f"Stock actualizado: +{request.quantity}", "product": state}


@app.get("/products")
async def list_products():
    products = await database.get_all_products()
    return {"total": len(products), "products": products}


@app.get("/products/{product_id}")
async def get_product(product_id: str):
    product_events = await database.get_events(product_id)
    if not product_events:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return evt.build_product_state(product_events)


@app.get("/products/{product_id}/history")
async def get_product_history(product_id: str):
    product_events = await database.get_events(product_id)
    if not product_events:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    return {
        "product_id":    product_id,
        "total_events":  len(product_events),
        "current_state": evt.build_product_state(product_events),
        "events": [
            {
                "version":     e["version"],
                "event_type":  e["event_type"],
                "occurred_at": e["occurred_at"].isoformat(),
                "payload":     e["payload"],
            }
            for e in product_events
        ],
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "inventory", "broker": "redis-streams"}
