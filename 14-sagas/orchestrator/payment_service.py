"""
Servicio de Pagos — Estilo Orquestación
Puerto: 8002

Recibe comandos HTTP directos del Orquestador Saga.

Comandos
--------
POST /payments              procesar un pago
POST /payments/{id}/refund  reembolsar un pago  (compensación)
"""

from __future__ import annotations
from pydantic import BaseModel
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

app = FastAPI(title="Servicio de Pagos (Orquestación)", version="1.0")

payments: Dict[str, dict] = {}
order_to_payment: Dict[str, str] = {}


class ProcessPaymentRequest(BaseModel):
    order_id: str
    amount: float
    customer_id: str


@app.post("/payments", status_code=201)
async def process_payment(req: ProcessPaymentRequest):
    """
    Simula el cobro al cliente.
    Devuelve HTTP 402 si el monto supera el umbral para que el orquestador
    inicie el flujo de compensación.
    """
    if req.amount > PAYMENT_FAILURE_THRESHOLD:
        logger.warning(
            "Pago RECHAZADO para pedido %s — %.2f > umbral %.2f",
            req.order_id, req.amount, PAYMENT_FAILURE_THRESHOLD,
        )
        raise HTTPException(
            status_code=402,
            detail=f"Payment declined: amount {req.amount:.2f} exceeds limit {PAYMENT_FAILURE_THRESHOLD:.2f}",
        )

    payment_id = str(uuid.uuid4())
    payment = {
        "payment_id": payment_id,
        "order_id": req.order_id,
        "amount": req.amount,
        "status": "COMPLETED",
    }
    payments[payment_id] = payment
    order_to_payment[req.order_id] = payment_id
    logger.info("Pago %s COMPLETADO para pedido %s", payment_id, req.order_id)
    return payment


@app.post("/payments/{payment_id}/refund")
async def refund_payment(payment_id: str):
    """Transacción compensatoria — llamada por el orquestador al revertir."""
    payment = payments.get(payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    payment["status"] = "REFUNDED"
    logger.info("Pago %s REEMBOLSADO", payment_id)
    return payment


@app.get("/payments/{payment_id}")
async def get_payment(payment_id: str):
    if payment_id not in payments:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    return payments[payment_id]


@app.get("/payments")
async def list_payments():
    return list(payments.values())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
