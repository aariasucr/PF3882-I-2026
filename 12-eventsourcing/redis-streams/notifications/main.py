"""
Servicio de Notificaciones — Event Sourcing con Redis Streams
==============================================================

Lee de AMBOS streams (orders e inventory) para capturar todos los eventos.

Con Redis Streams, múltiples consumer groups pueden leer el mismo stream
de forma independiente. Esto es fan-out nativo: inventory-cg y
notifications-cg leen stream:orders sin interferirse.

El stream conserva el historial completo → se puede hacer replay
para reconstruir el log de notificaciones desde cero.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

import database
import broker

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


TEMPLATES = {
    "OrderPlaced": (
        "🛒 Nuevo pedido #{order_id} del cliente {customer_id} "
        "por ${total:.2f} ({item_count} ítem(s))"
    ),
    "OrderConfirmed": "✅ Pedido #{order_id} CONFIRMADO",
    "OrderCancelled": "❌ Pedido #{order_id} CANCELADO — {reason}",
    "OrderShipped":   "🚚 Pedido #{order_id} ENVIADO — tracking: {tracking_number}",
    "StockReserved":  (
        "📦 Stock reservado: {quantity} ud. del producto {product_id} "
        "para pedido #{order_id}"
    ),
    "StockInsufficient": (
        "⚠️  Stock insuficiente para #{order_id}: "
        "pidieron {requested}, hay {available}"
    ),
    "StockReleased": (
        "🔓 Stock liberado: {quantity} ud. del producto {product_id} "
        "(pedido #{order_id} cancelado)"
    ),
}


def _render(event_type: str, payload: dict) -> str:
    template = TEMPLATES.get(event_type, "Evento {event_type}")
    try:
        context = {
            "event_type": event_type,
            "item_count": len(payload.get("items", [])),
            **payload,
        }
        return template.format(**context)
    except KeyError:
        return f"[{event_type}] {payload}"


async def handle_stream_event(payload: dict, stream: str):
    """
    Procesa eventos de cualquier stream.

    A diferencia de RabbitMQ donde el routing_key identifica el evento,
    aquí usamos payload["event_type"]. El parámetro `stream` indica
    de cuál stream proviene (orders o inventory).
    """
    event_type   = payload.get("event_type", "Unknown")
    aggregate_id = payload.get("order_id") or payload.get("product_id", "unknown")
    message      = _render(event_type, payload)

    await database.save_notification(
        event_type=event_type,
        aggregate_id=aggregate_id,
        message=message,
    )
    log.info("📬 [%s] %s", stream, message)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    await broker.connect()

    # Leer stream de orders con consumer group propio
    asyncio.create_task(
        broker.consume(
            stream=broker.STREAM_ORDERS,
            group="notifications-cg",
            consumer="notifications-orders-1",
            handler=handle_stream_event,
        )
    )

    # Leer stream de inventory con consumer group propio
    # Los dos consumer groups son independientes: cada uno recibe todos los mensajes
    asyncio.create_task(
        broker.consume(
            stream=broker.STREAM_INVENTORY,
            group="notifications-inventory-cg",
            consumer="notifications-inventory-1",
            handler=handle_stream_event,
        )
    )

    yield

    await broker.disconnect()
    await database.close_db()


app = FastAPI(
    title="Notifications Service",
    description="Microservicio de notificaciones con Event Sourcing + Redis Streams",
    lifespan=lifespan,
)


@app.get("/notifications")
async def list_notifications(limit: int = 50):
    notifications = await database.get_notifications(limit)
    return {"total": len(notifications), "notifications": notifications}


@app.get("/notifications/stats")
async def notification_stats():
    stats = await database.get_stats()
    return {"stats": stats}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "notifications", "broker": "redis-streams"}
