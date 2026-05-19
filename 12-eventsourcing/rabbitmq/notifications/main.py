"""
Servicio de Notificaciones — Event Sourcing con RabbitMQ
=========================================================

Este servicio demuestra uno de los grandes beneficios de Event Sourcing:
CUALQUIER servicio puede suscribirse al flujo de eventos y reaccionar,
sin que los servicios productores necesiten saber quién escucha.

El servicio de notificaciones no PRODUCE eventos, solo los CONSUME.
Registra cada evento de dominio como una notificación para el usuario.

En un sistema real, aquí enviarías emails, SMS, push notifications, etc.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

import database
import broker

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


# ─── Templates de notificación ────────────────────────────────────────────────

TEMPLATES = {
    "OrderPlaced": (
        "🛒 Nuevo pedido #{order_id} del cliente {customer_id} "
        "por ${total:.2f} ({item_count} ítem(s))"
    ),
    "OrderConfirmed": (
        "✅ Pedido #{order_id} CONFIRMADO — stock reservado exitosamente"
    ),
    "OrderCancelled": (
        "❌ Pedido #{order_id} CANCELADO — motivo: {reason}"
    ),
    "OrderShipped": (
        "🚚 Pedido #{order_id} ENVIADO — tracking: {tracking_number}"
    ),
    "StockReserved": (
        "📦 Stock reservado: {quantity} unidad(es) del producto "
        "{product_id} para pedido #{order_id}"
    ),
    "StockInsufficient": (
        "⚠️  Stock insuficiente para pedido #{order_id}: "
        "se pidieron {requested}, solo hay {available}"
    ),
    "StockReleased": (
        "🔓 Stock liberado: {quantity} unidad(es) del producto "
        "{product_id} (pedido #{order_id} cancelado)"
    ),
}


def _render(event_type: str, payload: dict) -> str:
    template = TEMPLATES.get(event_type, "Evento {event_type}: {payload_str}")
    try:
        context = {
            "event_type":  event_type,
            "item_count":  len(payload.get("items", [])),
            "payload_str": str(payload),
            **payload,
        }
        return template.format(**context)
    except KeyError:
        return f"[{event_type}] {payload}"


# ─── Handler de eventos ───────────────────────────────────────────────────────

async def handle_domain_event(payload: dict, routing_key: str):
    """
    Recibe cualquier evento de dominio y genera una notificación.

    El routing_key tiene la forma "servicio.evento" (ej: "orders.placed").
    El event_type está también en el payload para mayor claridad.
    """
    event_type   = payload.get("event_type", routing_key)
    aggregate_id = payload.get("order_id") or payload.get("product_id", "unknown")
    message      = _render(event_type, payload)

    await database.save_notification(
        event_type=event_type,
        aggregate_id=aggregate_id,
        message=message,
    )
    log.info("📬 %s", message)


# ─── Ciclo de vida ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    await broker.connect()

    # Suscribirse a TODOS los eventos usando wildcards de RabbitMQ
    # "orders.#" → cualquier evento del dominio orders
    # "inventory.#" → cualquier evento del dominio inventory
    asyncio.create_task(
        broker.consume(
            queue_name="notifications.all_domain_events",
            routing_keys=["orders.#", "inventory.#"],
            handler=handle_domain_event,
        )
    )

    yield

    await broker.disconnect()
    await database.close_db()


app = FastAPI(
    title="Notifications Service",
    description="Microservicio de notificaciones con Event Sourcing + RabbitMQ",
    lifespan=lifespan,
)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/notifications")
async def list_notifications(limit: int = 50):
    """
    Lista las últimas notificaciones.

    Cada notificación corresponde a un evento de dominio.
    El orden refleja la secuencia real de eventos en el sistema.
    """
    notifications = await database.get_notifications(limit)
    return {"total": len(notifications), "notifications": notifications}


@app.get("/notifications/stats")
async def notification_stats():
    """
    Estadísticas de eventos procesados por tipo.

    Útil para visualizar la actividad del sistema completo.
    """
    stats = await database.get_stats()
    return {"stats": stats}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "notifications", "broker": "rabbitmq"}
