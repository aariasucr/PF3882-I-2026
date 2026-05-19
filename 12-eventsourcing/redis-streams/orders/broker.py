"""
Broker Redis Streams - Servicio de Pedidos
==========================================
Redis Streams es un log de mensajes append-only, similar a Kafka.

Diferencias con RabbitMQ:
  RabbitMQ: Exchange → routing_key → Queue → Consumer
  Redis:    Stream  → Consumer Group → Consumer

Ventajas de Redis Streams:
  - Mensajes persisten en el stream (se puede releer el historial)
  - Consumer Groups garantizan at-least-once delivery
  - Fan-out: múltiples grupos leen el mismo stream independientemente
  - Integrado en Redis (sin infraestructura adicional si ya usas Redis)

Streams que usamos:
  stream:orders    → eventos del servicio de pedidos
  stream:inventory → eventos del servicio de inventario
"""

import redis.asyncio as aioredis
import json
import os
import asyncio
import logging
from typing import Callable

log = logging.getLogger(__name__)

REDIS_URL        = os.getenv("REDIS_URL", "redis://localhost:6379")
STREAM_ORDERS    = "stream:orders"
STREAM_INVENTORY = "stream:inventory"

_redis: aioredis.Redis = None


async def connect(retries: int = 15, delay: float = 2.0):
    global _redis
    for attempt in range(retries):
        try:
            _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
            await _redis.ping()
            log.info("✅ Conectado a Redis")
            return
        except Exception as exc:
            log.warning("Redis no disponible (intento %d/%d): %s",
                        attempt + 1, retries, exc)
            await asyncio.sleep(delay)
    raise RuntimeError("No se pudo conectar a Redis tras varios intentos")


async def disconnect():
    if _redis:
        await _redis.aclose()


async def publish(stream: str, payload: dict):
    """
    Publica un evento a un Redis Stream (XADD).

    Redis genera un ID único con timestamp: 1699000000000-0
    El ID garantiza el orden cronológico de los mensajes.
    """
    fields = {"data": json.dumps(payload, default=str)}
    msg_id = await _redis.xadd(stream, fields)
    log.info("📤 Publicado en %s [%s]", stream, msg_id)
    return msg_id


async def consume(
    stream:   str,
    group:    str,
    consumer: str,
    handler:  Callable,
    batch:    int = 10,
):
    """
    Consume mensajes desde un Redis Stream usando Consumer Groups.

    Consumer Groups:
    - Cada mensaje es procesado por EXACTAMENTE UN consumidor del grupo
    - Múltiples grupos en el mismo stream = fan-out (cada grupo recibe todo)
    - Los mensajes no-ACK quedan en "pending" y se pueden re-procesar
    - XACK confirma que el mensaje fue procesado correctamente

    Parámetros:
        stream:   nombre del stream (ej: "stream:orders")
        group:    nombre del consumer group (ej: "orders-cg")
        consumer: nombre de esta instancia (ej: "orders-1")
        handler:  función async(payload, stream) que procesa el mensaje
    """
    # Crear el consumer group (id="0" = leer desde el inicio del stream)
    try:
        await _redis.xgroup_create(stream, group, id="0", mkstream=True)
        log.info("✅ Consumer group '%s' creado en stream '%s'", group, stream)
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
        log.info("👥 Consumer group '%s' ya existe", group)

    log.info("👂 Escuchando '%s' como '%s/%s'", stream, group, consumer)

    while True:
        try:
            # ">" = solo mensajes que nadie en este grupo ha leído aún
            results = await _redis.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={stream: ">"},
                count=batch,
                block=1000,   # espera hasta 1s si el stream está vacío
            )

            if not results:
                continue

            for _stream_name, messages in results:
                for msg_id, fields in messages:
                    try:
                        payload = json.loads(fields["data"])
                        await handler(payload, stream)
                        # ACK: el mensaje fue procesado, sacarlo del pending list
                        await _redis.xack(stream, group, msg_id)
                    except Exception as exc:
                        log.error("Error procesando msg %s: %s", msg_id, exc)
                        # Sin XACK el mensaje permanece en pending list
                        # para ser re-procesado (XPENDING / XCLAIM)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            log.error("Error en consumidor [%s/%s]: %s", group, consumer, exc)
            await asyncio.sleep(1)
