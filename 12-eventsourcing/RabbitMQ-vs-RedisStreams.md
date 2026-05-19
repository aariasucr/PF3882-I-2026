# RabbitMQ vs Redis Streams — Comparación Detallada

> Ambas variantes implementan el mismo dominio: Orders, Inventory y Notifications con Event Sourcing.  
> Lo único que cambia es el mecanismo de mensajería — el event store, la lógica de negocio y los endpoints son idénticos.

---

## Modelo mental

|                 | RabbitMQ                                                                                       | Redis Streams                                                                                   |
| --------------- | ---------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| **Analogía**    | Servicio postal: el broker decide a quién entregar cada carta según la dirección (routing key) | Periódico compartido: todos leen el mismo diario; cada lector decide qué artículos le interesan |
| **Abstracción** | Message broker con enrutamiento                                                                | Log append-only distribuido                                                                     |
| **Similar a**   | ActiveMQ, Azure Service Bus, Google Pub/Sub                                                    | Apache Kafka, AWS Kinesis                                                                       |

---

## Arquitectura de mensajería

### RabbitMQ

```
Publisher
    │
    ▼
Exchange "domain_events"  (tipo TOPIC)
    │
    ├── routing_key "orders.placed"     ──► Queue "inventory.order_events"
    │                                   ──► Queue "notifications.all"
    │
    ├── routing_key "orders.shipped"    ──► Queue "inventory.order_events"
    │                                   ──► Queue "notifications.all"
    │
    └── routing_key "inventory.#"       ──► Queue "orders.inventory_responses"
                                        ──► Queue "notifications.all"
```

- El broker hace el routing: el publisher no sabe quién consume
- Cada consumer declara su propia queue con bindings específicos
- Los mensajes **desaparecen** de la queue tras ser consumidos y ACKed

### Redis Streams

```
Publisher
    │
    ▼
stream:orders  (log append-only)
    │
    ├── Consumer Group "inventory-cg"
    │       └── consumer "inventory-1"     ← filtra por event_type en el handler
    │
    └── Consumer Group "notifications-cg"
            └── consumer "notifications-orders-1"

stream:inventory  (log append-only)
    │
    ├── Consumer Group "orders-cg"
    │       └── consumer "orders-1"
    │
    └── Consumer Group "notifications-inventory-cg"
            └── consumer "notifications-inventory-1"
```

- El stream es un log compartido; los consumer groups reciben todos los mensajes
- Los mensajes **persisten** en el stream aunque sean consumidos
- El filtrado ocurre en el handler, no en el broker

---

## Diferencias en el código

### Publicar un evento

**RabbitMQ** — el tipo de evento va en el `routing_key`:

```python
# broker.py
await _exchange.publish(
    aio_pika.Message(body=json.dumps(payload).encode(),
                     delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
    routing_key="orders.placed",   # ← identifica el tipo de evento
)
```

**Redis Streams** — el tipo de evento va dentro del payload:

```python
# broker.py
await _redis.xadd(
    "stream:orders",               # ← solo identifica el stream
    {"data": json.dumps(payload)}  # event_type va dentro del payload
)
```

---

### Consumir eventos

**RabbitMQ** — el broker filtra; el handler recibe solo los mensajes que le corresponden:

```python
# broker.py
queue = await _channel.declare_queue("inventory.order_events", durable=True)
await queue.bind(_exchange, routing_key="orders.placed")
await queue.bind(_exchange, routing_key="orders.cancelled")
await queue.bind(_exchange, routing_key="orders.shipped")

# main.py — el routing_key ya actúa como filtro
async def handle_order_event(payload: dict, routing_key: str):
    if routing_key == "orders.placed":
        await _reserve_stock(payload)
    elif routing_key == "orders.cancelled":
        await _release_stock(payload)
    elif routing_key == "orders.shipped":
        await _ship_stock(payload)
```

**Redis Streams** — todos los eventos llegan; el handler filtra por `event_type`:

```python
# broker.py
results = await _redis.xreadgroup(
    groupname="inventory-cg",
    consumername="inventory-1",
    streams={"stream:orders": ">"},  # ">" = mensajes no vistos por este grupo
    count=10, block=1000
)
for msg_id, fields in results[0][1]:
    payload = json.loads(fields["data"])
    await handler(payload, "stream:orders")
    await _redis.xack("stream:orders", "inventory-cg", msg_id)

# main.py — el filtro es manual
async def handle_order_event(payload: dict, stream: str):
    event_type = payload.get("event_type")   # ← hay que leer el campo
    if event_type == "OrderPlaced":
        await _reserve_stock(payload)
    elif event_type == "OrderCancelled":
        await _release_stock(payload)
    elif event_type == "OrderShipped":
        await _ship_stock(payload)
```

---

### ACK (acknowledgment)

**RabbitMQ** — ACK/NACK por mensaje:

```python
async def on_message(message: aio_pika.IncomingMessage):
    try:
        await handler(json.loads(message.body), message.routing_key)
        await message.ack()           # elimina el mensaje de la queue
    except Exception:
        await message.reject(requeue=True)  # devuelve a la queue
```

**Redis Streams** — XACK confirma procesamiento, pero el mensaje queda en el stream:

```python
await _redis.xack("stream:orders", "inventory-cg", msg_id)
# El mensaje sigue en stream:orders — otros grupos aún pueden leerlo
# Sin XACK → queda en "pending list" → XPENDING lo muestra
```

---

## Tabla comparativa completa

| Característica           | RabbitMQ                                                | Redis Streams                                                |
| ------------------------ | ------------------------------------------------------- | ------------------------------------------------------------ |
| **Modelo**               | Message broker (push)                                   | Append-only log (pull/poll)                                  |
| **Routing**              | Exchange + routing keys + wildcards en el broker        | Sin routing; filtro manual por `event_type` en el handler    |
| **Historial**            | No: mensajes se eliminan tras ACK                       | Sí: el log persiste indefinidamente                          |
| **Replay**               | No posible                                              | Sí: `XRANGE stream:orders - +` o cambiando el ID de inicio   |
| **Fan-out**              | Una queue por suscriptor, todos con binding al exchange | Un consumer group por suscriptor; todos leen el mismo stream |
| **Filtrado**             | En el broker (routing key → queue binding)              | En el consumidor (`event_type` en el payload)                |
| **At-least-once**        | Sí: `reject(requeue=True)`                              | Sí: sin `XACK` el mensaje queda en pending list              |
| **Ordering**             | FIFO por queue                                          | Garantizado por ID de tiempo (`timestamp-sequence`)          |
| **Persistencia**         | Queues durable + mensajes persistent                    | AOF (append-only file) en disco                              |
| **Visibilidad**          | UI web en puerto 15672                                  | `redis-cli XINFO GROUPS stream:orders`                       |
| **Infraestructura**      | Servidor RabbitMQ dedicado                              | Redis (si ya está en el stack, costo cero)                   |
| **Complejidad de setup** | Exchange + queue + binding por cada suscriptor          | Stream + consumer group                                      |

---

## Flujo de eventos en cada implementación

### Ciclo de vida de un pedido — RabbitMQ

```
orders.placed ──────────────────────► inventory.order_events
                                       inventory.order_events
                                       notifications.all

inventory.stock_reserved ───────────► orders.inventory_responses
                                       notifications.all

inventory.stock_insufficient ───────► orders.inventory_responses
                                       notifications.all

orders.confirmed ───────────────────► notifications.all

orders.shipped ─────────────────────► inventory.order_events   (descuenta stock)
                                       notifications.all

inventory.stock_shipped ────────────► notifications.all

orders.cancelled ───────────────────► inventory.order_events   (libera stock)
                                       notifications.all

inventory.stock_released ───────────► notifications.all
```

### Ciclo de vida de un pedido — Redis Streams

```
stream:orders  ◄── OrderPlaced
               ◄── OrderConfirmed
               ◄── OrderCancelled  (lleva items)
               ◄── OrderShipped    (lleva items)

stream:inventory ◄── StockReserved
                 ◄── StockInsufficient
                 ◄── StockReleased
                 ◄── StockShipped

Consumer groups en stream:orders:
  inventory-cg        → filtra OrderPlaced / OrderCancelled / OrderShipped
  notifications-cg    → lee todos

Consumer groups en stream:inventory:
  orders-cg                   → filtra StockReserved / StockInsufficient
  notifications-inventory-cg  → lee todos
```

---

## Eventos de dominio y su impacto en el stock

| Evento              | Quién lo produce | Quién lo consume         | Efecto en stock                               |
| ------------------- | ---------------- | ------------------------ | --------------------------------------------- |
| `OrderPlaced`       | Orders           | Inventory, Notifications | —                                             |
| `StockReserved`     | Inventory        | Orders, Notifications    | `reserved_stock += qty`                       |
| `StockInsufficient` | Inventory        | Orders, Notifications    | —                                             |
| `OrderConfirmed`    | Orders           | Notifications            | —                                             |
| `OrderCancelled`    | Orders           | Inventory, Notifications | —                                             |
| `StockReleased`     | Inventory        | Notifications            | `reserved_stock -= qty`                       |
| `OrderShipped`      | Orders           | Inventory, Notifications | —                                             |
| `StockShipped`      | Inventory        | Notifications            | `reserved_stock -= qty`, `total_stock -= qty` |

> **Nota sobre `StockReleased` vs `StockShipped`:**
>
> - `StockReleased`: el pedido se canceló → el stock vuelve al pool disponible (`total_stock` no cambia)
> - `StockShipped`: el pedido se envió → los ítems salieron del almacén físicamente (`total_stock` baja)

---

## ¿Cuándo elegir cada uno?

### Elige RabbitMQ cuando…

- Necesitas routing complejo basado en atributos del mensaje (wildcards, headers)
- Los mensajes son **comandos** o **tareas** que debe procesar exactamente un consumidor
- El historial del broker no importa (los eventos ya están en tu event store)
- Tienes equipos usando múltiples lenguajes (Java, .NET, Python, Go) — AMQP es un protocolo estándar
- Quieres dead-letter queues, TTL por mensaje, y prioridades nativas
- No tienes Redis en el stack

### Elige Redis Streams cuando…

- El **replay** es importante: nuevos servicios deben procesar el historial completo al arrancar
- Quieres un **audit trail** permanente en el broker (no solo en el event store)
- Ya tienes Redis en el stack → costo operativo cero
- Necesitas fan-out a muchos consumer groups sin overhead de queues
- Las cargas son altas y la latencia baja es crítica
- Quieres inspeccionar el log directamente con `redis-cli`

### Para Event Sourcing puro

Redis Streams es más natural: el stream **es** un event log. La filosofía es la misma — append-only, ordenado, replay posible. RabbitMQ es mejor cuando los eventos son efímeros y el routing es la prioridad.

---

## Comandos útiles para inspeccionar cada broker

### RabbitMQ

```bash
# Ver queues y mensajes pendientes
curl -s http://guest:guest@localhost:15672/api/queues | python3 -m json.tool

# Ver exchanges
curl -s http://guest:guest@localhost:15672/api/exchanges | python3 -m json.tool

# UI web (más cómodo)
open http://localhost:15672  # user: guest / pass: guest
```

### Redis Streams

```bash
# Ver todos los eventos en el stream de orders
docker exec es_redis redis-cli XRANGE stream:orders - +

# Ver consumer groups del stream
docker exec es_redis redis-cli XINFO GROUPS stream:orders

# Ver mensajes pendientes (no ACKed) de un consumer group
docker exec es_redis redis-cli XPENDING stream:orders inventory-cg - + 10

# Contar mensajes en el stream
docker exec es_redis redis-cli XLEN stream:orders

# Replay desde el inicio para un consumer group
docker exec es_redis redis-cli XGROUP SETID stream:orders inventory-cg 0
```

---

## Archivos que cambian entre variantes

| Archivo                   | RabbitMQ                                         | Redis Streams                              |
| ------------------------- | ------------------------------------------------ | ------------------------------------------ |
| `broker.py`               | `aio_pika` · Exchange TOPIC · `routing_key`      | `redis.asyncio` · XADD · XREADGROUP · XACK |
| `requirements.txt`        | `aio-pika==9.4.3`                                | `redis[hiredis]==5.2.0`                    |
| `docker-compose.yml`      | Incluye servicio `rabbitmq:3.13-management`      | Incluye servicio `redis:7.4-alpine`        |
| `main.py` (inventory)     | Filtra por `routing_key`                         | Filtra por `payload["event_type"]`         |
| `main.py` (notifications) | Un `consume()` con `["orders.#", "inventory.#"]` | Dos `consume()` — uno por stream           |

**Todo lo demás es idéntico:** `events.py`, `database.py`, la lógica de negocio, los endpoints REST.
