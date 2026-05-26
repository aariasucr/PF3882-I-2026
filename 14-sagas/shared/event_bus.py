"""
Bus de eventos pub/sub en memoria.

En producción se reemplazaría con Redis Streams, Kafka, RabbitMQ, etc.
Para la demo en clase se mantiene todo en proceso para no requerir
dependencias externas.

Uso
---
    bus = EventBus()

    @bus.subscribe("order_created")
    async def handle(event):
        ...

    await bus.publish("order_created", event)
"""

from __future__ import annotations
import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine, Dict, List

logger = logging.getLogger(__name__)


class EventBus:
    """Bus pub/sub en proceso con entrega de eventos en amplitud (BFS).

    Los eventos publicados mientras los handlers están ejecutándose se
    encolan y se procesan después de que el lote actual de handlers
    termine. Esto imita el comportamiento de un bus real (Kafka,
    RabbitMQ, etc.): los eventos generados por un handler nunca se
    intercalan con los handlers del evento que los originó.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str,
                                List[Callable[..., Coroutine]]] = defaultdict(list)
        self._queue: list = []
        self._draining: bool = False

    def subscribe(self, event_type: str):
        """Decorador: registra un handler asíncrono para un tipo de evento."""
        def decorator(fn: Callable[..., Coroutine]):
            self._subscribers[event_type].append(fn)
            logger.info("Subscribed %s to '%s'", fn.__name__, event_type)
            return fn
        return decorator

    async def publish(self, event_type: str, event: Any) -> None:
        """Publica un evento; lo encola si ya hay un ciclo de drenado activo."""
        self._queue.append((event_type, event))
        if self._draining:
            return  # el ciclo de drenado externo lo procesará
        self._draining = True
        while self._queue:
            etype, evt = self._queue.pop(0)
            handlers = self._subscribers.get(etype, [])
            logger.info("Publishing '%s' to %d handler(s)", etype, len(handlers))
            for handler in handlers:
                try:
                    await handler(evt)
                except Exception as exc:
                    logger.exception(
                        "Handler %s failed for event '%s': %s",
                        handler.__name__, etype, exc,
                    )
        self._draining = False


# Bus singleton compartido por todos los servicios de coreografía en esta demo.
# Ambos estilos (coreografía y orquestación) importan esta misma instancia.
bus = EventBus()
