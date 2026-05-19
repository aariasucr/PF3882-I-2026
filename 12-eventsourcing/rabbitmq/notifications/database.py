"""
Base de datos - Servicio de Notificaciones
El servicio de notificaciones no tiene su propio event store de dominio,
solo un log de notificaciones enviadas.
"""

import asyncpg
import json
import os
from typing import List, Dict, Any, Optional

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://eventsource:eventsource@localhost/notifications_db"
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
            CREATE TABLE IF NOT EXISTS notification_log (
                id           BIGSERIAL    PRIMARY KEY,
                event_type   VARCHAR(100) NOT NULL,
                aggregate_id VARCHAR(36)  NOT NULL,
                message      TEXT         NOT NULL,
                sent_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_notif_event_type
                ON notification_log(event_type);
            CREATE INDEX IF NOT EXISTS idx_notif_aggregate
                ON notification_log(aggregate_id);
        """)


async def save_notification(
    event_type: str,
    aggregate_id: str,
    message: str,
) -> Dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO notification_log (event_type, aggregate_id, message)
            VALUES ($1, $2, $3)
            RETURNING *
        """, event_type, aggregate_id, message)
        return dict(row)


async def get_notifications(limit: int = 50) -> List[Dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, event_type, aggregate_id, message, sent_at
            FROM   notification_log
            ORDER  BY sent_at DESC
            LIMIT  $1
        """, limit)
        result = []
        for row in rows:
            d = dict(row)
            d["sent_at"] = d["sent_at"].isoformat()
            result.append(d)
        return result


async def get_stats() -> List[Dict]:
    """Estadísticas de eventos procesados agrupados por tipo"""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT event_type,
                   COUNT(*)::int                           AS total,
                   MAX(sent_at)                            AS last_seen
            FROM   notification_log
            GROUP  BY event_type
            ORDER  BY total DESC
        """)
        result = []
        for row in rows:
            d = dict(row)
            d["last_seen"] = d["last_seen"].isoformat()
            result.append(d)
        return result
