"""
Pruebas para ambos estilos de Saga.

Ejecutar con:  pytest tests/test_sagas.py -v

Todas las pruebas son asíncronas y usan AsyncClient de FastAPI.
No se requieren servicios externos — todo corre en proceso.
"""

from __future__ import annotations
from httpx import AsyncClient, ASGITransport
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def order_payload(skus: list[str], qty: int = 1, unit_price: float = 10.0) -> dict:
    return {
        "customer_id": "CUST-TEST-001",
        "items": [{"sku": s, "quantity": qty, "unit_price": unit_price} for s in skus],
    }


# ===========================================================================
# PRUEBAS DE COREOGRAFÍA
# ===========================================================================

@pytest.fixture(autouse=True)
def reset_choreography_state():
    """Limpia los almacenes en memoria antes de cada prueba."""
    import choreography.order_service as o
    import choreography.payment_service as p
    import choreography.inventory_service as i

    o.orders.clear()
    p.payments.clear()
    p.order_to_payment.clear()
    i.catalog.update({"SKU-001": 100, "SKU-002": 5, "SKU-OUT": 0})
    i.reservations.clear()
    i.order_to_reservation.clear()
    i._pending_items.clear()
    yield


@pytest.fixture
def choreo_order_app():
    import choreography.order_service as svc
    return svc.app


@pytest.fixture
def choreo_payment_app():
    import choreography.payment_service as svc
    return svc.app


@pytest.fixture
def choreo_inventory_app():
    import choreography.inventory_service as svc
    return svc.app


class TestChoreographyHappyPath:
    """Camino exitoso: pedido → pago → stock, todos exitosos."""

    @pytest.mark.asyncio
    async def test_order_created_and_confirmed(self, choreo_order_app):
        async with AsyncClient(
            transport=ASGITransport(app=choreo_order_app), base_url="http://test"
        ) as client:
            resp = await client.post("/orders", json=order_payload(["SKU-001"]))
            assert resp.status_code == 201
            data = resp.json()
            # el bus disparó pago e inventario de forma inline
            assert data["status"] == "CONFIRMED"
            assert "order_id" in data

    @pytest.mark.asyncio
    async def test_payment_collected_on_happy_path(self, choreo_order_app, choreo_payment_app):
        async with AsyncClient(
            transport=ASGITransport(app=choreo_order_app), base_url="http://test"
        ) as order_client:
            resp = await order_client.post("/orders", json=order_payload(["SKU-001"]))
            order_id = resp.json()["order_id"]

        import choreography.payment_service as p
        payment = next(
            (pmt for pmt in p.payments.values()
             if pmt["order_id"] == order_id), None
        )
        assert payment is not None
        assert payment["status"] == "COMPLETED"

    @pytest.mark.asyncio
    async def test_stock_reserved_on_happy_path(self, choreo_order_app):
        async with AsyncClient(
            transport=ASGITransport(app=choreo_order_app), base_url="http://test"
        ) as client:
            resp = await client.post("/orders", json=order_payload(["SKU-001"], qty=2))
            order_id = resp.json()["order_id"]

        import choreography.inventory_service as i
        res = next(
            (r for r in i.reservations.values()
             if r["order_id"] == order_id), None
        )
        assert res is not None
        assert res["status"] == "RESERVED"
        assert i.catalog["SKU-001"] == 98   # 100 - 2


class TestChoreographyPaymentFailure:
    """Escenario 1: pago rechazado (monto > 500) → pedido cancelado."""

    @pytest.mark.asyncio
    async def test_order_cancelled_when_payment_fails(self, choreo_order_app):
        # unit_price=600 → total=600 > umbral
        async with AsyncClient(
            transport=ASGITransport(app=choreo_order_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/orders", json=order_payload(["SKU-001"], unit_price=600.0)
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["status"] == "CANCELLED"
            assert "cancel_reason" in data

    @pytest.mark.asyncio
    async def test_no_stock_reservation_when_payment_fails(self, choreo_order_app):
        async with AsyncClient(
            transport=ASGITransport(app=choreo_order_app), base_url="http://test"
        ) as client:
            await client.post(
                "/orders", json=order_payload(["SKU-001"], unit_price=600.0)
            )

        import choreography.inventory_service as i
        assert len(i.reservations) == 0
        assert i.catalog["SKU-001"] == 100   # sin cambios


class TestChoreographyStockFailure:
    """Escenario 2: pago exitoso, stock no disponible → reembolso + cancelación."""

    @pytest.mark.asyncio
    async def test_order_cancelled_when_stock_unavailable(self, choreo_order_app):
        async with AsyncClient(
            transport=ASGITransport(app=choreo_order_app), base_url="http://test"
        ) as client:
            resp = await client.post("/orders", json=order_payload(["SKU-OUT"]))
            assert resp.status_code == 201
            data = resp.json()
            assert data["status"] == "CANCELLED"

    @pytest.mark.asyncio
    async def test_payment_refunded_when_stock_unavailable(self, choreo_order_app):
        async with AsyncClient(
            transport=ASGITransport(app=choreo_order_app), base_url="http://test"
        ) as client:
            await client.post("/orders", json=order_payload(["SKU-OUT"]))

        import choreography.payment_service as p
        for payment in p.payments.values():
            assert payment["status"] == "REFUNDED"


# ===========================================================================
# PRUEBAS DE ORQUESTACIÓN
# ===========================================================================

@pytest.fixture(autouse=True)
def reset_orchestration_state():
    import orchestrator.order_service as o
    import orchestrator.payment_service as p
    import orchestrator.inventory_service as i
    from orchestrator.saga_state import saga_registry

    o.orders.clear()
    p.payments.clear()
    p.order_to_payment.clear()
    i.catalog.update({"SKU-001": 100, "SKU-002": 5, "SKU-OUT": 0})
    i.reservations.clear()
    saga_registry.clear()
    yield


@pytest.fixture
def orchestrator_app():
    import orchestrator.main as m
    return m.app


class TestOrchestratorHappyPath:

    @pytest.mark.asyncio
    async def test_saga_completes(self, orchestrator_app):
        async with AsyncClient(
            transport=ASGITransport(app=orchestrator_app), base_url="http://test"
        ) as client:
            resp = await client.post("/saga/start", json=order_payload(["SKU-001"]))
            assert resp.status_code == 201
            data = resp.json()
            assert data["step"] == "COMPLETED"
            assert data["payment_id"] is not None
            assert data["reservation_id"] is not None

    @pytest.mark.asyncio
    async def test_saga_history_recorded(self, orchestrator_app):
        async with AsyncClient(
            transport=ASGITransport(app=orchestrator_app), base_url="http://test"
        ) as client:
            resp = await client.post("/saga/start", json=order_payload(["SKU-001"]))
            data = resp.json()
            steps = [h["to"] for h in data["history"]]
            assert "ORDER_CREATED" in steps
            assert "PAYMENT_PROCESSED" in steps
            assert "STOCK_RESERVED" in steps
            assert "COMPLETED" in steps

    @pytest.mark.asyncio
    async def test_get_saga_by_id(self, orchestrator_app):
        async with AsyncClient(
            transport=ASGITransport(app=orchestrator_app), base_url="http://test"
        ) as client:
            resp = await client.post("/saga/start", json=order_payload(["SKU-001"]))
            saga_id = resp.json()["saga_id"]

            get_resp = await client.get(f"/saga/{saga_id}")
            assert get_resp.status_code == 200
            assert get_resp.json()["saga_id"] == saga_id


class TestOrchestratorPaymentFailure:

    @pytest.mark.asyncio
    async def test_saga_fails_on_payment_declined(self, orchestrator_app):
        async with AsyncClient(
            transport=ASGITransport(app=orchestrator_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/saga/start", json=order_payload(["SKU-001"], unit_price=600.0)
            )
            data = resp.json()
            assert data["step"] == "FAILED"
            assert "Payment" in data["failure_reason"]

    @pytest.mark.asyncio
    async def test_order_cancelled_when_payment_fails(self, orchestrator_app):
        async with AsyncClient(
            transport=ASGITransport(app=orchestrator_app), base_url="http://test"
        ) as client:
            await client.post(
                "/saga/start", json=order_payload(["SKU-001"], unit_price=600.0)
            )

        import orchestrator.order_service as o
        for order in o.orders.values():
            assert order["status"] == "CANCELLED"

    @pytest.mark.asyncio
    async def test_compensation_steps_in_history(self, orchestrator_app):
        async with AsyncClient(
            transport=ASGITransport(app=orchestrator_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/saga/start", json=order_payload(["SKU-001"], unit_price=600.0)
            )
            steps = [h["to"] for h in resp.json()["history"]]
            assert "CANCELLING_ORDER" in steps
            assert "FAILED" in steps


class TestOrchestratorStockFailure:

    @pytest.mark.asyncio
    async def test_saga_fails_on_stock_unavailable(self, orchestrator_app):
        async with AsyncClient(
            transport=ASGITransport(app=orchestrator_app), base_url="http://test"
        ) as client:
            resp = await client.post("/saga/start", json=order_payload(["SKU-OUT"]))
            data = resp.json()
            assert data["step"] == "FAILED"

    @pytest.mark.asyncio
    async def test_payment_refunded_when_stock_unavailable(self, orchestrator_app):
        async with AsyncClient(
            transport=ASGITransport(app=orchestrator_app), base_url="http://test"
        ) as client:
            await client.post("/saga/start", json=order_payload(["SKU-OUT"]))

        import orchestrator.payment_service as p
        for payment in p.payments.values():
            assert payment["status"] == "REFUNDED"

    @pytest.mark.asyncio
    async def test_full_compensation_chain_in_history(self, orchestrator_app):
        async with AsyncClient(
            transport=ASGITransport(app=orchestrator_app), base_url="http://test"
        ) as client:
            resp = await client.post("/saga/start", json=order_payload(["SKU-OUT"]))
            steps = [h["to"] for h in resp.json()["history"]]
            # Debe mostrar: ORDER_CREATED → PAYMENT_PROCESSED → REFUNDING_PAYMENT
            #               → CANCELLING_ORDER → FAILED
            assert "ORDER_CREATED" in steps
            assert "PAYMENT_PROCESSED" in steps
            assert "REFUNDING_PAYMENT" in steps
            assert "CANCELLING_ORDER" in steps
            assert "FAILED" in steps
