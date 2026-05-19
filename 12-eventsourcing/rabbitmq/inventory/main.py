"""
Servicio de Inventario — Event Sourcing con RabbitMQ
=====================================================

Responsabilidades:
  - Registrar productos y su stock inicial
  - Escuchar OrderPlaced → reservar stock → publicar StockReserved/StockInsufficient
  - Escuchar OrderCancelled → liberar stock → publicar StockReleased
  - Exponer estado del inventario (reconstruido desde eventos)

Conceptos que demuestra:
  - Event Sourcing para movimientos de inventario (igual que un libro mayor)
  - El stock = suma de todos los movimientos, no un número directo
  - Participación en la Saga coreografiada
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


# ─── Modelos de entrada ───────────────────────────────────────────────────────

class CreateProductRequest(BaseModel):
    name:          str
    price:         float
    initial_stock: int


class AddStockRequest(BaseModel):
    quantity: int
    reason:   str = "Reposición de inventario"


# ─── Saga Handler: reacciona a eventos de pedidos ────────────────────────────

async def handle_order_event(payload: dict, routing_key: str):
    """
    Implementa el lado 'inventory' de la Saga de pedido.

    OrderPlaced    → intenta reservar stock para cada ítem del pedido
    OrderCancelled → libera el stock reservado
    """
    if routing_key == "orders.placed":
        await _reserve_stock(payload)
    elif routing_key == "orders.cancelled":
        await _release_stock(payload)
    elif routing_key == "orders.shipped":
        await _ship_stock(payload)


async def _reserve_stock(order_payload: dict):
    """
    Intenta reservar stock para todos los ítems del pedido.

    Si CUALQUIER ítem no tiene stock suficiente, falla todo el pedido
    (comportamiento transaccional en una saga distribuida).
    """
    order_id = order_payload["order_id"]
    items    = order_payload.get("items", [])

    for item in items:
        product_id = item["product_id"]
        quantity   = item["quantity"]

        # Reconstruir estado actual del producto desde sus eventos
        product_events = await database.get_events(product_id)

        if not product_events:
            event = evt.StockInsufficient(
                order_id=order_id,
                product_id=product_id,
                requested=quantity,
                available=0,
                reason=f"Producto '{item.get('product_name', product_id)}' no existe en inventario",
            )
            version = await database.get_next_version(order_id)
            await database.save_event(
                order_id, "Reservation", event.event_type, event.model_dump(), version
            )
            await broker.publish("inventory.stock_insufficient", event.model_dump())
            log.warning("❌ Producto no encontrado para pedido %s", order_id)
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
            await broker.publish("inventory.stock_insufficient", event.model_dump())
            log.warning("❌ Stock insuficiente para pedido %s", order_id)
            return

        # Hay stock: reservar
        next_version  = await database.get_next_version(product_id)
        reserve_event = evt.StockReserved(
            order_id=order_id, product_id=product_id, quantity=quantity
        )
        await database.save_event(
            product_id, "Product", reserve_event.event_type,
            reserve_event.model_dump(), next_version
        )

        # Actualizar proyección
        new_product_events = await database.get_events(product_id)
        new_state          = evt.build_product_state(new_product_events)
        await database.upsert_product_projection(new_state)

        await broker.publish("inventory.stock_reserved", reserve_event.model_dump())
        log.info("✅ Reservadas %d unidades de '%s' para pedido %s",
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

        await broker.publish("inventory.stock_shipped", ship_event.model_dump())
        log.info("🚚 Despachadas %d unidades para pedido %s", quantity, order_id)


async def _release_stock(order_payload: dict):
    """Libera el stock que fue reservado cuando el pedido se cancela"""
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

        await broker.publish("inventory.stock_released", release_event.model_dump())
        log.info("🔓 Liberadas %d unidades para pedido %s", quantity, order_id)


# ─── Ciclo de vida ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    await broker.connect()

    asyncio.create_task(
        broker.consume(
            queue_name="inventory.order_events",
            routing_keys=["orders.placed", "orders.cancelled", "orders.shipped"],
            handler=handle_order_event,
        )
    )

    yield

    await broker.disconnect()
    await database.close_db()


app = FastAPI(
    title="Inventory Service",
    description="Microservicio de inventario con Event Sourcing + RabbitMQ",
    lifespan=lifespan,
)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/products", status_code=201)
async def create_product(request: CreateProductRequest):
    """Comando: Registrar un nuevo producto con stock inicial"""
    product_id = str(uuid.uuid4())

    event = evt.ProductCreated(
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
    """Comando: Reponer stock de un producto"""
    product_events = await database.get_events(product_id)
    if not product_events:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    next_version = await database.get_next_version(product_id)
    event        = evt.StockAdded(
        product_id=product_id,
        quantity=request.quantity,
        reason=request.reason,
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
    """Lista todos los productos desde la proyección"""
    products = await database.get_all_products()
    return {"total": len(products), "products": products}


@app.get("/products/{product_id}")
async def get_product(product_id: str):
    """
    Estado actual del producto reconstruido desde sus eventos.

    El stock disponible = stock total − stock reservado,
    calculado sumando todos los eventos de movimiento.
    """
    product_events = await database.get_events(product_id)
    if not product_events:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    return evt.build_product_state(product_events)


@app.get("/products/{product_id}/history")
async def get_product_history(product_id: str):
    """
    Historial de movimientos de stock del producto.

    Cada reserva, reposición y liberación queda registrada para siempre.
    Puedes reconstruir el stock en cualquier momento histórico.
    """
    product_events = await database.get_events(product_id)
    if not product_events:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    return {
        "product_id":    product_id,
        "total_events":  len(product_events),
        "current_state": evt.build_product_state(product_events),
        "events": [
            {
                "version":    e["version"],
                "event_type": e["event_type"],
                "occurred_at": e["occurred_at"].isoformat(),
                "payload":    e["payload"],
            }
            for e in product_events
        ],
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "inventory", "broker": "rabbitmq"}
