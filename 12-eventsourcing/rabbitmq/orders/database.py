"""
Event Store + Proyecciones - Servicio de Pedidos
=================================================
El Event Store es una base de datos APPEND-ONLY.
Nunca se actualizan ni eliminan registros.

Las proyecciones son vistas derivadas optimizadas para lectura (CQRS).
"""

import asyncpg
import json
import os
from typing import List, Dict, Any, Optional

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://eventsource:eventsource@localhost/orders_db"
)

pool: Optional[asyncpg.Pool] = None


async def init_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    await _create_tables()


async def close_db():
    if pool:
        await pool.close()


async def _create_tables():
    async with pool.acquire() as conn:
        await conn.execute("""
            -- EVENT STORE: tabla append-only, nunca se modifica
            CREATE TABLE IF NOT EXISTS events (
                id             BIGSERIAL    PRIMARY KEY,
                aggregate_id   VARCHAR(36)  NOT NULL,
                aggregate_type VARCHAR(100) NOT NULL,
                event_type     VARCHAR(100) NOT NULL,
                payload        JSONB        NOT NULL,
                version        INTEGER      NOT NULL,
                occurred_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                -- Garantiza orden correcto y evita escrituras concurrentes
                UNIQUE(aggregate_id, version)
            );

            CREATE INDEX IF NOT EXISTS idx_events_aggregate
                ON events(aggregate_id, version);

            -- PROYECCIÓN: tabla desnormalizada para consultas rápidas (CQRS)
            -- Se reconstruye a partir de los eventos, no es la fuente de verdad
            CREATE TABLE IF NOT EXISTS order_projections (
                id              VARCHAR(36)   PRIMARY KEY,
                customer_id     VARCHAR(100)  NOT NULL,
                items           JSONB         NOT NULL,
                status          VARCHAR(50)   NOT NULL DEFAULT 'PENDING',
                total           DECIMAL(10,2) NOT NULL,
                tracking_number VARCHAR(100),
                created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
                updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
            );
        """)


async def save_event(
    aggregate_id: str,
    aggregate_type: str,
    event_type: str,
    payload: Dict[str, Any],
    version: int,
) -> Dict:
    """
    Persiste un evento en el event store.

    IMPORTANTE: Esta es la única operación de escritura permitida.
    No hay UPDATE ni DELETE en el event store.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO events
                (aggregate_id, aggregate_type, event_type, payload, version)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            RETURNING id, aggregate_id, aggregate_type, event_type,
                      payload, version, occurred_at
        """, aggregate_id, aggregate_type, event_type,
            json.dumps(payload), version)
        return dict(row)


async def get_events(aggregate_id: str) -> List[Dict]:
    """
    Obtiene todos los eventos de un aggregate en orden cronológico.
    Estos eventos se usan para reconstruir el estado actual.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, aggregate_id, aggregate_type, event_type,
                   payload, version, occurred_at
            FROM   events
            WHERE  aggregate_id = $1
            ORDER  BY version ASC
        """, aggregate_id)
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]


async def get_next_version(aggregate_id: str) -> int:
    """Obtiene el siguiente número de versión para un aggregate"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT COALESCE(MAX(version), 0) + 1 AS next_version
            FROM   events
            WHERE  aggregate_id = $1
        """, aggregate_id)
        return row["next_version"]


async def upsert_order_projection(order: Dict):
    """
    Actualiza la proyección de lectura con el estado actual del pedido.

    La proyección es opcional: si se corrompe, se puede reconstruir
    reproduciendo todos los eventos del event store (replay).
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO order_projections
                (id, customer_id, items, status, total, tracking_number, updated_at)
            VALUES ($1, $2, $3::jsonb, $4, $5, $6, NOW())
            ON CONFLICT (id) DO UPDATE SET
                status          = EXCLUDED.status,
                tracking_number = EXCLUDED.tracking_number,
                updated_at      = NOW()
        """,
            order["id"],
            order["customer_id"],
            json.dumps(order["items"]),
            order["status"],
            order["total"],
            order.get("tracking_number"),
        )


async def get_all_orders() -> List[Dict]:
    """
    Lista todos los pedidos desde la proyección (lectura rápida).

    Patrón CQRS: las lecturas van a la proyección,
    las escrituras van al event store.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, customer_id, items, status, total,
                   tracking_number, created_at, updated_at
            FROM   order_projections
            ORDER  BY created_at DESC
        """)
        result = []
        for row in rows:
            d = dict(row)
            d["created_at"] = d["created_at"].isoformat()
            d["updated_at"] = d["updated_at"].isoformat()
            result.append(d)
        return result
