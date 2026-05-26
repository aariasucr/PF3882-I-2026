"""
Runner de la demo de Coreografía.

Monta los tres servicios bajo una única aplicación ASGI para poder ejecutar
el ejemplo completo de coreografía con un solo comando:

    python choreography/main.py

Los endpoints están organizados así:
    /orders/*      → Servicio de Pedidos
    /payments/*    → Servicio de Pagos
    /inventory/*   → Servicio de Inventario (catálogo, reservas)
    /docs          → Swagger UI combinado
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Importar los tres servicios — esto también registra todos los suscriptores del bus
import choreography.order_service as _order        # noqa: F401
import choreography.payment_service as _payment    # noqa: F401
import choreography.inventory_service as _inv      # noqa: F401

from fastapi import FastAPI
from fastapi.routing import Mount
from starlette.applications import Starlette

app = FastAPI(
    title="Saga — Estilo Coreografía",
    description=(
        "Los tres servicios comparten un bus de eventos en proceso. "
        "Usa POST /orders para iniciar una saga."
    ),
    version="1.0",
)

# Montar sub-aplicaciones
app.mount("/orders-svc",    _order.app)
app.mount("/payments-svc",  _payment.app)
app.mount("/inventory-svc", _inv.app)

# Re-rutas de conveniencia en el nivel raíz para facilitar las pruebas
from fastapi import Request
from fastapi.responses import JSONResponse

# Re-exportar rutas de pedidos en el nivel raíz
app.include_router(_order.app.router,   prefix="")
app.include_router(_payment.app.router, prefix="")
app.include_router(_inv.app.router,     prefix="")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "choreography.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
