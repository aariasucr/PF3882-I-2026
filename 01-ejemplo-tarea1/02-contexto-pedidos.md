# Contexto delimitado: Pedidos (Order Management)

## Tabla de contenidos

- [Descripción](#descripción)
- [Responsabilidades](#responsabilidades)
- [Lenguaje ubicuo](#lenguaje-ubicuo)
- [Modelo del dominio](#modelo-del-dominio)
  - [Snapshot: OrderItem](#snapshot-orderitem)
  - [Estados típicos del pedido](#estados-típicos-del-pedido)
- [Eventos](#eventos)
  - [Eventos emitidos](#eventos-emitidos-publicados-por-este-contexto)
  - [Eventos consumidos](#eventos-consumidos-de-otros-contextos)
- [Diagramas](#diagramas)
  - [Comunicación interna](#comunicación-interna-del-contexto)
  - [Agregados y flujo de estados](#agregados-y-flujo-de-estados)
  - [Modelo de datos interno](#modelo-de-datos-interno)
  - [Comunicación con otros contextos](#comunicación-con-otros-contextos-delimitados)
  - [Secuencia: de checkout a envío](#secuencia-con-eventos-de-checkout-a-envío)
- [Resumen](#resumen)

---

## Descripción

El contexto de **Pedidos** gestiona la **intención de compra**: creación de pedidos, ítems comprados, totales, estados e historial. Aquí un "producto" no es el producto completo del catálogo, sino un **snapshot** (copia en el momento del pedido) para fijar precio y nombre aunque el catálogo cambie después.

## Responsabilidades

- **Crear pedidos** a partir del carrito o checkout.
- Gestionar el **estado del pedido** (CREATED, PAID, SHIPPED, CANCELLED).
- Mantener **ítems comprados** con precio y cantidad.
- Calcular y almacenar **totales**.
- Conservar **historial** del ciclo de vida del pedido.

## Lenguaje ubicuo

| Término      | Significado en este contexto                           |
| ------------ | ------------------------------------------------------ |
| **Pedido**   | Intención de compra con ítems y estado                 |
| **Checkout** | Proceso de confirmación antes de crear el pedido       |
| **Carrito**  | Conjunto de ítems pendientes de confirmar (pre-pedido) |
| **Estado**   | CREATED, PAID, SHIPPED, CANCELLED                      |

## Modelo del dominio

### Snapshot: OrderItem

En este contexto un "producto" es solo una **copia en el momento de la compra**:

```
OrderItem {
  productId,
  nombreProducto,
  precioAlMomento,
  cantidad
}
```

El pedido guarda el **precio histórico** aunque el catálogo cambie después.

### Estados típicos del pedido

| Estado        | Descripción                                    |
| ------------- | ---------------------------------------------- |
| **CREATED**   | Pedido creado, pendiente de pago               |
| **PAID**      | Pago confirmado                                |
| **SHIPPED**   | Marcado como enviado (coordinación con Envíos) |
| **CANCELLED** | Pedido cancelado                               |

---

## Eventos

### Eventos emitidos (publicados por este contexto)

| Evento            | Descripción                                         | Consumidores típicos                                         |
| ----------------- | --------------------------------------------------- | ------------------------------------------------------------ |
| `PedidoCreado`    | Nuevo pedido con ítems y totales                    | Envíos (para preparar envío), notificaciones                 |
| `PedidoPagado`    | Pago confirmado; pedido listo para enviar           | Envíos (crear envío/paquete)                                 |
| `PedidoCancelado` | Pedido cancelado                                    | Envíos (cancelar envío), Catálogo (devolver stock si aplica) |
| `PedidoEnviado`   | Pedido marcado como enviado (puede venir de Envíos) | Notificaciones, reporting                                    |

### Eventos consumidos (de otros contextos)

| Evento                                                            | Origen   | Uso en Pedidos                                   |
| ----------------------------------------------------------------- | -------- | ------------------------------------------------ |
| `ProductoPublicado`, `PrecioActualizado`, `ProductoDescontinuado` | Catálogo | Validar ítems en carrito y al hacer checkout     |
| `EnvioEntregado` (opcional)                                       | Envíos   | Pasar pedido a estado "entregado" o cerrar ciclo |

---

## Diagramas

### Comunicación interna del contexto

Flujo: carrito → checkout → pedido → estados.

```mermaid
flowchart TB
    subgraph Pedidos["Contexto: Pedidos"]
        direction TB
        A[Servicio Carrito] --> B[Servicio Checkout]
        B --> C[Agregado Pedido]
        C --> D[(Repositorio Pedidos)]
        E[Servicio de Estados] --> C
        F[API Pedidos] --> A
        F --> B
        F --> E
        G[Publicador de Eventos] --> C
    end

    C -->|PedidoCreado / PedidoPagado / PedidoCancelado| G
```

### Agregados y flujo de estados

```mermaid
stateDiagram-v2
    [*] --> CREATED: PedidoCreado
    CREATED --> PAID: PedidoPagado
    CREATED --> CANCELLED: PedidoCancelado
    PAID --> SHIPPED: PedidoEnviado
    SHIPPED --> [*]
    CANCELLED --> [*]
```

### Modelo de datos interno

```mermaid
erDiagram
    PEDIDO ||--|{ ORDER_ITEM : "contiene"
    PEDIDO {
        string id PK
        string clienteId
        string estado
        decimal total
        datetime createdAt
    }
    ORDER_ITEM {
        string id PK
        string pedidoId FK
        string productId
        string nombreProducto
        decimal precioAlMomento
        int cantidad
    }
```

### Comunicación con otros contextos delimitados

Pedidos **consume** datos del Catálogo (consulta) y **publica** eventos que Envíos usa para crear y gestionar envíos.

```mermaid
flowchart LR
    subgraph Catalogo["Catálogo de Productos"]
        API_CAT[API Consulta]
    end

    subgraph Pedidos["Pedidos"]
        CP[Checkout / Pedido]
        EV_P[Eventos: PedidoCreado, PedidoPagado, etc.]
    end

    subgraph Envios["Envíos"]
        CREAR_ENV[Crear Envío]
    end

    CP -->|Consulta producto, precio| API_CAT
    EV_P -->|Suscrito| CREAR_ENV
```

### Secuencia con eventos: de checkout a envío

```mermaid
sequenceDiagram
    participant Cliente
    participant Pedidos as Contexto Pedidos
    participant Catalogo as Contexto Catálogo
    participant Envios as Contexto Envíos
    participant Bus as Bus de Eventos

    Cliente->>Pedidos: Checkout (productIds, cantidades)
    Pedidos->>Catalogo: API: obtener productos y precios
    Catalogo-->>Pedidos: Datos actuales
    Pedidos->>Pedidos: Crear Pedido (snapshots OrderItem)
    Pedidos->>Bus: PedidoCreado(orderId, items, total, direccion)
    Pedidos->>Bus: PedidoPagado(orderId, direccionEnvio)
    Bus->>Envios: PedidoPagado
    Envios->>Envios: Crear Shipment
    Envios->>Bus: EnvioCreado(orderId, trackingNumber)
    Bus->>Pedidos: (opcional) actualizar estado
```

---

## Resumen

| Aspecto             | Detalle                                                                                    |
| ------------------- | ------------------------------------------------------------------------------------------ |
| **Responsabilidad** | Gestionar intención de compra: pedidos, ítems, totales, estados                            |
| **Producto**        | Snapshot: OrderItem (productId, nombreProducto, precioAlMomento, cantidad)                 |
| **Estados**         | CREATED → PAID → SHIPPED, o CANCELLED                                                      |
| **Comunicación**    | Consulta Catálogo; publica PedidoCreado, PedidoPagado, PedidoCancelado para Envíos y otros |
