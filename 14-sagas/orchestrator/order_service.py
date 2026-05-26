"""
Servicio de Pedidos — Estilo Orquestación
Puerto: 8001

En el patrón de orquestación este servicio es un simple ejecutor de comandos.
NO se suscribe a eventos de otros servicios — solo responde a comandos HTTP
directos emitidos por el Orquestador Saga.

Comandos
--------
POST /orders                   crear un pedido  (paso 1)
POST /orders/{id}/cancel       cancelar un pedido  (compensación)
"""

from __future__ import annotations
from shared.events import OrderItem
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from typing import Dict, List
import logging
import uuid
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [PEDIDOS] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Servicio de Pedidos (Orquestación)", version="1.0")

orders: Dict[str, dict] = {}


class CreateOrderRequest(BaseModel):
    order_id: str           # suministrado por el orquestador para correlación
    customer_id: str
    items: List[OrderItem]
    total_amount: float


class CancelOrderRequest(BaseModel):
    reason: str


@app.post("/orders", status_code=201)
async def create_order(req: CreateOrderRequest):
    order = {
        "order_id": req.order_id,
        "customer_id": req.customer_id,
        "items": [i.model_dump() for i in req.items],
        "total_amount": req.total_amount,
        "status": "PENDING",
    }
    orders[req.order_id] = order
    logger.info("Pedido %s creado", req.order_id)
    return order


@app.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, req: CancelOrderRequest):
    """Transacción compensatoria — llamada por el orquestador al revertir."""
    order = orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    order["status"] = "CANCELLED"
    order["cancel_reason"] = req.reason
    logger.info("Pedido %s CANCELADO: %s", order_id, req.reason)
    return order


@app.post("/orders/{order_id}/confirm")
async def confirm_order(order_id: str):
    """Marca el pedido como confirmado — llamada por el orquestador al completar."""
    order = orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    order["status"] = "CONFIRMED"
    logger.info("Pedido %s CONFIRMADO", order_id)
    return order


@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return orders[order_id]


@app.get("/orders")
async def list_orders():
    return list(orders.values())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
