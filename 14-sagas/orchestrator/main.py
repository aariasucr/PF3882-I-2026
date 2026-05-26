"""
Orquestador Saga — el coordinador central
Puerto: 8000

Este es el núcleo del patrón de orquestación. El orquestador posee la
máquina de estados de la saga y llama a cada servicio paso a paso usando
peticiones HTTP directas (simuladas aquí como llamadas en proceso por
simplicidad; en producción serían llamadas HTTP reales).

El orquestador es el ÚNICO lugar que conoce el flujo completo:
    1. Crear pedido
    2. Procesar pago
    3. Reservar stock
    → Completado

Y el flujo de compensación (en orden inverso):
    stock no disponible  →  reembolsar pago  →  cancelar pedido  →  Fallido
    pago fallido         →  cancelar pedido                      →  Fallido
"""

from __future__ import annotations
from shared.events import OrderItem
from orchestrator.saga_state import SagaInstance, SagaStep, saga_registry
import orchestrator.inventory_service as inventory_svc
import orchestrator.payment_service as payment_svc
import orchestrator.order_service as order_svc
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from typing import List
import logging
import uuid
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# Los tres servicios se importan directamente (en producción serían
# procesos separados accesibles por HTTP con httpx/requests)


logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [ORQUESTADOR] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Orquestador Saga",
    description="Coordinador central para la saga de cumplimiento de pedidos.",
    version="1.0",
)

# ---------------------------------------------------------------------------
# Helpers HTTP en proceso
# (Reemplazar con llamadas httpx reales cuando los servicios corran separados)
# ---------------------------------------------------------------------------


async def _call_create_order(saga: SagaInstance) -> dict:
    from orchestrator.order_service import CreateOrderRequest
    req = CreateOrderRequest(
        order_id=saga.order_id,
        customer_id=saga.customer_id,
        items=[OrderItem(**i) for i in saga.items],
        total_amount=saga.total_amount,
    )
    return await order_svc.create_order(req)


async def _call_cancel_order(saga: SagaInstance, reason: str) -> dict:
    from orchestrator.order_service import CancelOrderRequest
    return await order_svc.cancel_order(saga.order_id, CancelOrderRequest(reason=reason))


async def _call_confirm_order(saga: SagaInstance) -> dict:
    return await order_svc.confirm_order(saga.order_id)


async def _call_process_payment(saga: SagaInstance) -> dict:
    from orchestrator.payment_service import ProcessPaymentRequest
    req = ProcessPaymentRequest(
        order_id=saga.order_id,
        amount=saga.total_amount,
        customer_id=saga.customer_id,
    )
    return await payment_svc.process_payment(req)


async def _call_refund_payment(saga: SagaInstance) -> dict:
    return await payment_svc.refund_payment(saga.payment_id)


async def _call_reserve_stock(saga: SagaInstance) -> dict:
    from orchestrator.inventory_service import ReserveStockRequest, ReservationItem
    req = ReserveStockRequest(
        order_id=saga.order_id,
        items=[ReservationItem(sku=i["sku"], quantity=i["quantity"])
               for i in saga.items],
    )
    return await inventory_svc.reserve_stock(req)


async def _call_release_stock(saga: SagaInstance) -> dict:
    return await inventory_svc.release_stock(saga.reservation_id)


# ---------------------------------------------------------------------------
# Motor de ejecución de la saga
# ---------------------------------------------------------------------------

async def run_saga(saga: SagaInstance) -> None:
    """
    Avanza la saga a través de sus pasos.
    En caso de fallo, ejecuta los pasos de compensación en orden inverso.
    """
    logger.info("=== Saga %s INICIADA ===", saga.saga_id)

    # ------------------------------------------------------------------
    # Paso 1: Crear pedido
    # ------------------------------------------------------------------
    try:
        await _call_create_order(saga)
        saga.transition(SagaStep.ORDER_CREATED, "Pedido creado exitosamente")
        logger.info("[%s] Paso 1/3 — Pedido creado", saga.saga_id)
    except Exception as exc:
        saga.transition(SagaStep.FAILED, f"Error al crear pedido: {exc}")
        saga.failure_reason = str(exc)
        logger.error("[%s] FALLIDO en Paso 1 — %s", saga.saga_id, exc)
        return

    # ------------------------------------------------------------------
    # Paso 2: Procesar pago
    # ------------------------------------------------------------------
    try:
        result = await _call_process_payment(saga)
        saga.payment_id = result["payment_id"]
        saga.transition(SagaStep.PAYMENT_PROCESSED, "Pago cobrado")
        logger.info("[%s] Paso 2/3 — Pago procesado (%s)",
                    saga.saga_id, saga.payment_id)
    except HTTPException as exc:
        saga.failure_reason = exc.detail
        saga.transition(SagaStep.CANCELLING_ORDER,
                        f"Pago fallido: {exc.detail}")
        logger.warning(
            "[%s] Pago fallido — compensando: cancelar pedido", saga.saga_id)

        # Compensación: cancelar el pedido
        await _call_cancel_order(saga, reason=f"Pago fallido: {exc.detail}")
        saga.transition(SagaStep.FAILED, "Saga fallida tras pago rechazado")
        return

    # ------------------------------------------------------------------
    # Paso 3: Reservar stock
    # ------------------------------------------------------------------
    try:
        result = await _call_reserve_stock(saga)
        saga.reservation_id = result["reservation_id"]
        saga.transition(SagaStep.STOCK_RESERVED, "Stock reservado")
        logger.info("[%s] Paso 3/3 — Stock reservado (%s)",
                    saga.saga_id, saga.reservation_id)
    except HTTPException as exc:
        saga.failure_reason = exc.detail
        saga.transition(SagaStep.REFUNDING_PAYMENT,
                        f"Stock no disponible: {exc.detail}")
        logger.warning(
            "[%s] Stock no disponible — compensando: reembolsar + cancelar pedido", saga.saga_id)

        # Compensación paso A: reembolsar pago
        await _call_refund_payment(saga)
        saga.transition(SagaStep.CANCELLING_ORDER, "Pago reembolsado")

        # Compensación paso B: cancelar pedido
        await _call_cancel_order(saga, reason=f"Stock no disponible: {exc.detail}")
        saga.transition(SagaStep.FAILED, "Saga fallida tras stock no disponible")
        return

    # ------------------------------------------------------------------
    # Todos los pasos exitosos — confirmar el pedido
    # ------------------------------------------------------------------
    await _call_confirm_order(saga)
    saga.transition(SagaStep.COMPLETED, "Todos los pasos completados exitosamente")
    logger.info("=== Saga %s COMPLETADA ===", saga.saga_id)


# ---------------------------------------------------------------------------
# API REST
# ---------------------------------------------------------------------------

class StartSagaRequest(BaseModel):
    customer_id: str
    items: List[OrderItem]


@app.post("/saga/start", status_code=201)
async def start_saga(req: StartSagaRequest):
    """
    Inicia una nueva saga de cumplimiento de pedido.

    Este es el único punto de entrada para los clientes — nunca llaman
    directamente a los servicios individuales.
    """
    saga_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    total = sum(i.unit_price * i.quantity for i in req.items)

    saga = SagaInstance(
        saga_id=saga_id,
        order_id=order_id,
        customer_id=req.customer_id,
        items=[i.model_dump() for i in req.items],
        total_amount=total,
    )
    saga_registry[saga_id] = saga

    await run_saga(saga)
    return saga.to_dict()


@app.get("/saga/{saga_id}")
async def get_saga(saga_id: str):
    """Inspecciona el estado de una saga."""
    saga = saga_registry.get(saga_id)
    if not saga:
        raise HTTPException(status_code=404, detail="Saga no encontrada")
    return saga.to_dict()


@app.get("/sagas")
async def list_sagas():
    return [s.to_dict() for s in saga_registry.values()]


# Exponer también los endpoints de lectura de cada servicio para inspección
app.include_router(order_svc.app.router,
                   prefix="/svc/orders",       tags=["Servicio de Pedidos"])
app.include_router(payment_svc.app.router,
                   prefix="/svc/payments",     tags=["Servicio de Pagos"])
app.include_router(inventory_svc.app.router,
                   prefix="/svc/inventory",    tags=["Servicio de Inventario"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "orchestrator.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
