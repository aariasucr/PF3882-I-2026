# Explicación: test_sagas.py

## Resumen General

El archivo `tests/test_sagas.py` contiene un conjunto completo de pruebas **unitarias y de integración** para ambos patrones de Saga implementados en el proyecto:

1. **Coreografía** (Choreography): Las entidades se comunican entre sí de forma distribuida
2. **Orquestación** (Orchestration): Un orquestador central coordina todos los pasos

Todas las pruebas son **asincrónicas** y usan `AsyncClient` de FastAPI para simular solicitudes HTTP sin requerir servicios externos — todo corre en proceso.

---

## Ejecución

```bash
pytest tests/test_sagas.py -v
```

---

## Estructura del Archivo

### 1. **Helpers** (líneas 22-26)

```python
def order_payload(skus: list[str], qty: int = 1, unit_price: float = 10.0) -> dict
```

Función auxiliar que genera un payload de orden de prueba con:

- `customer_id`: identificador del cliente
- `items`: lista de artículos con SKU, cantidad y precio unitario

Se usa en todas las pruebas para crear órdenes consistentes.

---

## Pruebas de COREOGRAFÍA (líneas 30-171)

### **Fixture: `reset_choreography_state`** (líneas 33-47)

Ejecuta **antes de cada prueba** para limpiar el estado en memoria:

- Limpia órdenes, pagos, reservaciones
- Reestablece catálogo: `SKU-001: 100`, `SKU-002: 5`, `SKU-OUT: 0`
- Asegura que cada prueba comience con estado limpio

### **TestChoreographyHappyPath** (líneas 68-114)

✅ **Camino exitoso**: orden → pago → stock, todos exitosos

| Prueba                                 | Qué verifica                                                              |
| -------------------------------------- | ------------------------------------------------------------------------- |
| `test_order_created_and_confirmed`     | Orden creada con estado `CONFIRMED` (pago e inventario disparados inline) |
| `test_payment_collected_on_happy_path` | Pago registrado con estado `COMPLETED`                                    |
| `test_stock_reserved_on_happy_path`    | Stock reservado y catálogo actualizado (100 - 2 = 98)                     |

### **TestChoreographyPaymentFailure** (líneas 117-145)

❌ **Escenario de fallo**: Pago rechazado (monto > $500)

| Prueba                                         | Qué verifica                                |
| ---------------------------------------------- | ------------------------------------------- |
| `test_order_cancelled_when_payment_fails`      | Orden cancelada con `reason` de cancelación |
| `test_no_stock_reservation_when_payment_fails` | Sin reserva de stock (catálogo sin cambios) |

**Trigger**: Usar `unit_price=600.0` supera el umbral de $500

### **TestChoreographyStockFailure** (líneas 148-171)

❌ **Escenario de fallo**: Pago exitoso, pero stock no disponible → reembolso

| Prueba                                         | Qué verifica                         |
| ---------------------------------------------- | ------------------------------------ |
| `test_order_cancelled_when_stock_unavailable`  | Orden cancelada                      |
| `test_payment_refunded_when_stock_unavailable` | Pago reembolsado (estado `REFUNDED`) |

**Trigger**: Usar SKU inexistente (`SKU-OUT` = 0 stock)

---

## Pruebas de ORQUESTACIÓN (líneas 174-315)

### **Fixture: `reset_orchestration_state`** (líneas 177-190)

Ejecuta **antes de cada prueba** para limpiar el estado del orquestador:

- Limpia órdenes, pagos, reservaciones
- Limpia registro de sagas (`saga_registry`)
- Similar a coreografía pero incluye la limpieza de la máquina de estados

### **TestOrchestratorHappyPath** (líneas 199-236)

✅ **Camino exitoso**: Saga completa todos los pasos

| Prueba                       | Qué verifica                                                                                          |
| ---------------------------- | ----------------------------------------------------------------------------------------------------- |
| `test_saga_completes`        | Saga termina en estado `COMPLETED` con IDs de pago y reserva                                          |
| `test_saga_history_recorded` | Historial de pasos registrado: `ORDER_CREATED` → `PAYMENT_PROCESSED` → `STOCK_RESERVED` → `COMPLETED` |
| `test_get_saga_by_id`        | Se puede recuperar la saga por ID mediante GET `/saga/{saga_id}`                                      |

### **TestOrchestratorPaymentFailure** (líneas 239-276)

❌ **Escenario de fallo**: Pago rechazado

| Prueba                                    | Qué verifica                                                               |
| ----------------------------------------- | -------------------------------------------------------------------------- |
| `test_saga_fails_on_payment_declined`     | Saga termina en estado `FAILED` con `failure_reason`                       |
| `test_order_cancelled_when_payment_fails` | Orden compensada (cancelada)                                               |
| `test_compensation_steps_in_history`      | Historial incluye pasos de **compensación**: `CANCELLING_ORDER` → `FAILED` |

**Diferencia clave vs Coreografía**: El orquestador ejecuta explícitamente los pasos de compensación cuando una saga falla.

### **TestOrchestratorStockFailure** (líneas 279-314)

❌ **Escenario de fallo**: Stock no disponible (después de pago exitoso)

| Prueba                                         | Qué verifica                                                                                |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `test_saga_fails_on_stock_unavailable`         | Saga termina en `FAILED`                                                                    |
| `test_payment_refunded_when_stock_unavailable` | Pago reembolsado como compensación                                                          |
| `test_full_compensation_chain_in_history`      | Historial muestra **cadena completa de compensación**:                                      |
|                                                | `ORDER_CREATED` → `PAYMENT_PROCESSED` → `REFUNDING_PAYMENT` → `CANCELLING_ORDER` → `FAILED` |

---

## Comparación: Coreografía vs Orquestación

| Aspecto          | Coreografía                        | Orquestación                              |
| ---------------- | ---------------------------------- | ----------------------------------------- |
| **Control**      | Distribuido (cada servicio decide) | Centralizado (orquestador coordina)       |
| **Visibilidad**  | Implícita en los eventos           | Explícita en el historial (`history`)     |
| **Compensación** | Automática por cada servicio       | Orquestada paso a paso                    |
| **Prueba**       | Verifica estado final de servicios | Verifica transiciones de saga + historial |

---

## Patrones de Prueba Observados

1. **Fixtures con `autouse=True`**: Se ejecutan automáticamente antes de cada prueba
2. **AsyncClient + ASGITransport**: Simula HTTP sin servidor real
3. **Importaciones inline**: `import choreography.order_service as o` dentro de las pruebas para acceder al estado en memoria
4. **Verificación de estado compartido**: Las pruebas acceden a diccionarios en memoria (`orders`, `payments`, `reservations`) para verificar efectos secundarios
5. **Uso de assertions simples**: `assert status_code == 201`, `assert data["status"] == "CONFIRMED"`

---

## Casos Críticos Cubiertos

- ✅ Happy path (todo exitoso)
- ✅ Pago fallido (fallo temprano)
- ✅ Stock no disponible (fallo tardío con compensación)
- ✅ Historia de eventos / máquina de estados
- ✅ Recuperación de sagas por ID
