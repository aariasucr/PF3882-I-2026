"""
Event Store + Proyecciones - Servicio de Inventario
"""

import asyncpg
import json
import os
from typing import List, Dict, Any, Optional

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://eventsource:eventsource@localhost/inventory_db"
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
            CREATE TABLE IF NOT EXISTS events (
                id             BIGSERIAL    PRIMARY KEY,
                aggregate_id   VARCHAR(36)  NOT NULL,
                aggregate_type VARCHAR(100) NOT NULL,
                event_type     VARCHAR(100) NOT NULL,
                payload        JSONB        NOT NULL,
                version        INTEGER      NOT NULL,
                occurred_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                UNIQUE(aggregate_id, version)
            );

            CREATE INDEX IF NOT EXISTS idx_events_aggregate
                ON events(aggregate_id, version);

            -- Proyección de productos para consultas rápidas
            CREATE TABLE IF NOT EXISTS product_projections (
                id             VARCHAR(36)   PRIMARY KEY,
                name           VARCHAR(200)  NOT NULL,
                price          DECIMAL(10,2) NOT NULL DEFAULT 0,
                total_stock    INTEGER       NOT NULL DEFAULT 0,
                reserved_stock INTEGER       NOT NULL DEFAULT 0,
                updated_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
            );
        """)


async def save_event(
    aggregate_id: str,
    aggregate_type: str,
    event_type: str,
    payload: Dict[str, Any],
    version: int,
) -> Dict:
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
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT COALESCE(MAX(version), 0) + 1 AS next_version
            FROM   events
            WHERE  aggregate_id = $1
        """, aggregate_id)
        return row["next_version"]


async def upsert_product_projection(product: Dict):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO product_projections
                (id, name, price, total_stock, reserved_stock, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (id) DO UPDATE SET
                name           = EXCLUDED.name,
                price          = EXCLUDED.price,
                total_stock    = EXCLUDED.total_stock,
                reserved_stock = EXCLUDED.reserved_stock,
                updated_at     = NOW()
        """,
            product["id"],
            product["name"],
            product["price"],
            product["total_stock"],
            product["reserved_stock"],
        )


async def get_all_products() -> List[Dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, name, price, total_stock, reserved_stock,
                   (total_stock - reserved_stock) AS available_stock,
                   updated_at
            FROM   product_projections
            ORDER  BY name
        """)
        result = []
        for row in rows:
            d = dict(row)
            d["updated_at"] = d["updated_at"].isoformat()
            result.append(d)
        return result
