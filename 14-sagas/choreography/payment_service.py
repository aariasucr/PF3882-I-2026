"""
Servicio de Pagos — Estilo Coreografía
Puerto: 8002

Responsabilidades
-----------------
* Escuchar order_created     →  intentar cobrar al cliente
  - éxito  →  publicar PaymentCompletedEvent
  - fallo  →  publicar PaymentFailedEvent  (dispara compensación en otros servicios)
* Escuchar order_cancelled   →  reembolsar si ya se cobró un pago
  →  publicar PaymentRefundedEvent

Simulación de fallos
--------------------
Los pedidos con total_amount > PAYMENT_FAILURE_THRESHOLD son rechazados.
Configura la variable de entorno PAYMENT_FAILURE_THRESHOLD para cambiarlo (por defecto 500).
"""

from __future__ import annotations
from shared.event_bus import bus
from shared.events import (
    OrderCreatedEvent, OrderCancelledEvent,
    PaymentCompletedEvent, PaymentFailedEvent, PaymentRefundedEvent,
)
from fastapi import FastAPI, HTTPException
from typing import Dict
import logging
import uuid
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [PAGOS] %(message)s")
logger = logging.getLogger(__name__)

PAYMENT_FAILURE_THRESHOLD = float(
    os.getenv("PAYMENT_FAILURE_THRESHOLD", "500"))

app = FastAPI(title="Servicio de Pagos (Coreografía)", version="1.0")

# ---------------------------------------------------------------------------
# Almacén en memoria  {payment_id: registro_pago}
# ---------------------------------------------------------------------------
payments: Dict[str, dict] = {}          # clave: payment_id
order_to_payment: Dict[str, str] = {}   # order_id → payment_id


# ---------------------------------------------------------------------------
# Endpoints REST (solo lectura; las mutaciones ocurren vía eventos)
# ---------------------------------------------------------------------------

@app.get("/payments/{payment_id}")
async def get_payment(payment_id: str):
    if payment_id not in payments:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    return payments[payment_id]


@app.get("/payments")
async def list_payments():
    return list(payments.values())


# ---------------------------------------------------------------------------
# Handlers de eventos
# ---------------------------------------------------------------------------

@bus.subscribe("order_created")
async def on_order_created(event: OrderCreatedEvent):
    """Intenta cobrar al cliente cuando se crea un pedido."""
    logger.info(
        "Procesando pago para pedido %s (monto=%.2f)",
        event.order_id, event.total_amount,
    )

    # Simula fallo de pago para pedidos de monto elevado
    if event.total_amount > PAYMENT_FAILURE_THRESHOLD:
        logger.warning(
            "Pago RECHAZADO para pedido %s — monto %.2f supera umbral %.2f",
            event.order_id, event.total_amount, PAYMENT_FAILURE_THRESHOLD,
        )
        await bus.publish(
            "payment_failed",
            PaymentFailedEvent(
                order_id=event.order_id,
                reason=f"Monto {event.total_amount:.2f} supera límite {PAYMENT_FAILURE_THRESHOLD:.2f}",
            ),
        )
        return

    payment_id = str(uuid.uuid4())
    payment = {
        "payment_id": payment_id,
        "order_id": event.order_id,
        "amount": event.total_amount,
        "status": "COMPLETED",
    }
    payments[payment_id] = payment
    order_to_payment[event.order_id] = payment_id
    logger.info("Pago %s COMPLETADO para pedido %s",
                payment_id, event.order_id)

    await bus.publish(
        "payment_completed",
        PaymentCompletedEvent(
            order_id=event.order_id,
            payment_id=payment_id,
            amount=event.total_amount,
        ),
    )


@bus.subscribe("order_cancelled")
async def on_order_cancelled(event: OrderCancelledEvent):
    """Transacción compensatoria: reembolsa el pago si ya se cobró."""
    payment_id = order_to_payment.get(event.order_id)
    if not payment_id:
        logger.info(
            "No hay pago para el pedido %s — nada que reembolsar", event.order_id)
        return

    payment = payments[payment_id]
    if payment["status"] == "REFUNDED":
        return  # idempotente

    payment["status"] = "REFUNDED"
    logger.info("Pago %s REEMBOLSADO para pedido %s", payment_id, event.order_id)

    await bus.publish(
        "payment_refunded",
        PaymentRefundedEvent(order_id=event.order_id, payment_id=payment_id),
    )


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
