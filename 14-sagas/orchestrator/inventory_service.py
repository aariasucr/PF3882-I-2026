"""
Servicio de Inventario — Estilo Orquestación
Puerto: 8003

Recibe comandos HTTP directos del Orquestador Saga.

Comandos
--------
POST /reservations                     reservar stock
POST /reservations/{id}/release        liberar stock  (compensación)
"""

from __future__ import annotations
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from typing import Dict, List
import logging
import uuid
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [INVENTARIO] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Servicio de Inventario (Orquestación)", version="1.0")

catalog: Dict[str, int] = {
    "SKU-001": 100,
    "SKU-002": 5,
    "SKU-OUT": 0,   # intencionalmente sin stock
}

reservations: Dict[str, dict] = {}


class ReservationItem(BaseModel):
    sku: str
    quantity: int


class ReserveStockRequest(BaseModel):
    order_id: str
    items: List[ReservationItem]


@app.post("/reservations", status_code=201)
async def reserve_stock(req: ReserveStockRequest):
    """
    Intenta reservar los ítems.
    Devuelve HTTP 409 si algún ítem no está disponible.
    """
    # Validar primero — verificación todo-o-nada
    for item in req.items:
        available = catalog.get(item.sku, 0)
        if available < item.quantity:
            logger.warning(
                "Stock NO DISPONIBLE para pedido %s: %s tiene %d, necesita %d",
                req.order_id, item.sku, available, item.quantity,
            )
            raise HTTPException(
                status_code=409,
                detail=f"SKU {item.sku} only has {available} units (need {item.quantity})",
            )

    # Descontar
    for item in req.items:
        catalog[item.sku] -= item.quantity

    reservation_id = str(uuid.uuid4())
    reservation = {
        "reservation_id": reservation_id,
        "order_id": req.order_id,
        "items": [i.model_dump() for i in req.items],
        "status": "RESERVED",
    }
    reservations[reservation_id] = reservation
    logger.info("Reserva %s creada para pedido %s",
                reservation_id, req.order_id)
    return reservation


@app.post("/reservations/{reservation_id}/release")
async def release_stock(reservation_id: str):
    """Transacción compensatoria — llamada por el orquestador al revertir."""
    reservation = reservations.get(reservation_id)
    if not reservation:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    if reservation["status"] == "RELEASED":
        return reservation  # idempotente

    for item in reservation["items"]:
        catalog[item["sku"]] = catalog.get(item["sku"], 0) + item["quantity"]

    reservation["status"] = "RELEASED"
    logger.info("Reserva %s LIBERADA", reservation_id)
    return reservation


@app.get("/catalog")
async def get_catalog():
    return catalog


@app.get("/reservations")
async def list_reservations():
    return list(reservations.values())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
