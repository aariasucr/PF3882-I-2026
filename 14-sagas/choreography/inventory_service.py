"""
Servicio de Inventario — Estilo Coreografía
Puerto: 8003

Responsabilidades
-----------------
* Escuchar payment_completed  →  intentar reservar stock
  - éxito  →  publicar StockReservedEvent
  - fallo  →  publicar StockUnavailableEvent  (dispara cancelación y reembolso)
* Escuchar order_cancelled    →  liberar la reserva si existe

Catálogo
--------
Pre-cargado con un catálogo pequeño en memoria para la demo.
SKU-OUT está intencionalmente sin stock para demostrar el flujo de fallo.
"""

from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import uuid
import logging
from typing import Dict

from fastapi import FastAPI, HTTPException

from shared.events import (
    PaymentCompletedEvent, OrderCancelledEvent,
    StockReservedEvent, StockUnavailableEvent, StockReleasedEvent,
)
from shared.event_bus import bus

logging.basicConfig(level=logging.INFO, format="%(asctime)s [INVENTARIO] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Servicio de Inventario (Coreografía)", version="1.0")

# ---------------------------------------------------------------------------
# Catálogo en memoria  {sku: cantidad_disponible}
# ---------------------------------------------------------------------------
catalog: Dict[str, int] = {
    "SKU-001": 100,   # siempre disponible
    "SKU-002": 5,     # stock limitado
    "SKU-OUT": 0,     # deliberadamente sin stock
}

# Reservas  {reservation_id: {"order_id": ..., "items": [...]}}
reservations: Dict[str, dict] = {}
order_to_reservation: Dict[str, str] = {}


# ---------------------------------------------------------------------------
# Endpoints REST
# ---------------------------------------------------------------------------

@app.get("/catalog")
async def get_catalog():
    return catalog


@app.get("/reservations")
async def list_reservations():
    return list(reservations.values())


@app.get("/reservations/{reservation_id}")
async def get_reservation(reservation_id: str):
    if reservation_id not in reservations:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    return reservations[reservation_id]


# ---------------------------------------------------------------------------
# Handlers de eventos
# ---------------------------------------------------------------------------

@bus.subscribe("payment_completed")
async def on_payment_completed(event: PaymentCompletedEvent):
    """Intenta reservar stock después de un pago exitoso."""
    # Necesitamos los ítems del pedido original.
    # En un sistema real, el evento de pago incluiría una referencia y
    # consultaríamos el servicio de pedidos. Para simplificar, escuchamos
    # order_created también (ver abajo) y mantenemos una caché local.
    logger.info("Reservando stock para pedido %s", event.order_id)

    items = _pending_items.pop(event.order_id, [])
    if not items:
        logger.error("No se encontraron ítems pendientes para pedido %s", event.order_id)
        return

    # Verificar disponibilidad
    for item in items:
        available = catalog.get(item["sku"], 0)
        if available < item["quantity"]:
            logger.warning(
                "Stock NO DISPONIBLE para pedido %s: SKU %s tiene %d, necesita %d",
                event.order_id, item["sku"], available, item["quantity"],
            )
            await bus.publish(
                "stock_unavailable",
                StockUnavailableEvent(
                    order_id=event.order_id,
                    reason=f"SKU {item['sku']} solo tiene {available} unidades (necesita {item['quantity']})",
                ),
            )
            return

    # Descontar del catálogo
    for item in items:
        catalog[item["sku"]] -= item["quantity"]

    reservation_id = str(uuid.uuid4())
    reservation = {
        "reservation_id": reservation_id,
        "order_id": event.order_id,
        "items": items,
        "status": "RESERVED",
    }
    reservations[reservation_id] = reservation
    order_to_reservation[event.order_id] = reservation_id
    logger.info("Stock RESERVADO (%s) para pedido %s", reservation_id, event.order_id)

    await bus.publish(
        "stock_reserved",
        StockReservedEvent(order_id=event.order_id, reservation_id=reservation_id),
    )


# Caché de ítems desde order_created para tenerlos cuando llegue payment_completed
_pending_items: Dict[str, list] = {}

from shared.events import OrderCreatedEvent  # noqa: E402

@bus.subscribe("order_created")
async def on_order_created(event: OrderCreatedEvent):
    """Guarda en caché los ítems del pedido para usarlos cuando llegue el pago."""
    _pending_items[event.order_id] = [i.model_dump() for i in event.items]


@bus.subscribe("order_cancelled")
async def on_order_cancelled(event):
    """Transacción compensatoria: libera la reserva si existe."""
    reservation_id = order_to_reservation.get(event.order_id)
    if not reservation_id:
        _pending_items.pop(event.order_id, None)
        return

    reservation = reservations[reservation_id]
    if reservation["status"] == "RELEASED":
        return  # idempotente

    # Devolver ítems al catálogo
    for item in reservation["items"]:
        catalog[item["sku"]] = catalog.get(item["sku"], 0) + item["quantity"]

    reservation["status"] = "RELEASED"
    logger.info("Reserva %s LIBERADA para pedido %s", reservation_id, event.order_id)

    await bus.publish(
        "stock_released",
        StockReleasedEvent(order_id=event.order_id, reservation_id=reservation_id),
    )


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
