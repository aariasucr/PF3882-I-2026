"""
Broker RabbitMQ - Servicio de Pedidos
======================================
RabbitMQ usa el modelo de EXCHANGE + QUEUE:
- Exchange: recibe todos los eventos y los distribuye
- Routing key: etiqueta del evento (ej: "orders.placed")
- Queue: buzón de cada consumidor, con sus bindings
- Binding: suscripción de una queue a routing keys del exchange

Tipo TOPIC: permite wildcards (* = una palabra, # = cero o más palabras)
  "orders.*"  → orders.placed, orders.confirmed, orders.cancelled...
  "*.placed"  → orders.placed, tickets.placed...
"""

import aio_pika
import json
import os
import asyncio
import logging
from typing import Callable, List

log = logging.getLogger(__name__)

RABBITMQ_URL  = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq/")
EXCHANGE_NAME = "domain_events"

_connection: aio_pika.abc.AbstractRobustConnection = None
_channel:    aio_pika.abc.AbstractChannel           = None
_exchange:   aio_pika.abc.AbstractExchange          = None


async def connect(retries: int = 15, delay: float = 3.0):
    global _connection, _channel, _exchange
    for attempt in range(retries):
        try:
            _connection = await aio_pika.connect_robust(RABBITMQ_URL)
            _channel    = await _connection.channel()
            await _channel.set_qos(prefetch_count=10)
            _exchange   = await _channel.declare_exchange(
                EXCHANGE_NAME,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )
            log.info("✅ Conectado a RabbitMQ")
            return
        except Exception as exc:
            log.warning("RabbitMQ no disponible (intento %d/%d): %s",
                        attempt + 1, retries, exc)
            await asyncio.sleep(delay)
    raise RuntimeError("No se pudo conectar a RabbitMQ tras varios intentos")


async def disconnect():
    if _connection and not _connection.is_closed:
        await _connection.close()


async def publish(routing_key: str, payload: dict):
    """
    Publica un evento al exchange de dominio.

    El exchange distribuirá el mensaje a todas las queues
    que tengan un binding que coincida con el routing_key.
    """
    body = json.dumps(payload, default=str).encode()
    message = aio_pika.Message(
        body=body,
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,  # sobrevive reinicios
        content_type="application/json",
    )
    await _exchange.publish(message, routing_key=routing_key)
    log.info("📤 Publicado [%s]", routing_key)


async def consume(
    queue_name:   str,
    routing_keys: List[str],
    handler:      Callable,
):
    """
    Configura una queue durable y la suscribe a los routing_keys indicados.

    La queue es DURABLE: los mensajes sobreviven reinicios del broker.
    El ACK manual garantiza at-least-once delivery.
    """
    queue = await _channel.declare_queue(queue_name, durable=True)

    for rk in routing_keys:
        await queue.bind(_exchange, routing_key=rk)

    async def on_message(message: aio_pika.IncomingMessage):
        try:
            payload     = json.loads(message.body.decode())
            routing_key = message.routing_key
            log.info("📥 Recibido [%s]", routing_key)
            await handler(payload, routing_key)
            await message.ack()
        except Exception as exc:
            log.error("Error procesando [%s]: %s", routing_key, exc)
            await message.reject(requeue=True)

    await queue.consume(on_message)
    log.info("👂 Escuchando cola '%s' → %s", queue_name, routing_keys)
