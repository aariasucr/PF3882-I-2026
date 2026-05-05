# Tipos de prueba en este proyecto

Este proyecto contiene cuatro categorías de prueba distintas, cada una con un propósito
diferente y un nivel distinto de la arquitectura.

```
tests/
├── unit/           → capa de datos y lógica de negocio (sin HTTP)
│   ├── test_repository.py
│   └── test_service.py
├── api/            → endpoints HTTP funcionales + propiedad
│   ├── test_flask_api.py
│   ├── test_fastapi_api.py
│   ├── test_graphql_api.py
│   └── test_schemathesis.py
└── pact/           → contratos entre consumidor y proveedor
    ├── test_flask_pact.py
    └── test_fastapi_pact.py
```

---

## 1. Pruebas unitarias — `tests/unit/`

### 1.1 `test_repository.py` — Capa de acceso a datos (DAL)

**¿Qué prueba?**
Llama directamente a `TaskListRepository` y `TaskRepository` con una sesión SQLAlchemy
apuntando a una base de datos SQLite en memoria. Verifica que las operaciones CRUD
(create, read, update, delete) funcionen correctamente a nivel de modelo ORM.

**¿Qué cubre?**

- Que `create` persiste el objeto y asigna un `id` autogenerado.
- Que `get_all` devuelve todos los registros (con y sin filtro).
- Que `get_by_id` carga relaciones con `joinedload` (tareas dentro de una lista).
- Que `update` modifica el campo `updated_at` sin tocar `created_at`.
- Que `delete` elimina el registro y en cascada borra las tareas hijas.
- Que buscar un id inexistente devuelve `None` / `False`.

**¿Para qué sirve?**

- Detectar bugs en las consultas SQL/ORM antes de que lleguen a la API.
- Ejecutar en milisegundos sin levantar ningún servidor.
- Documentar el contrato de la interfaz del repositorio (tipos devueltos, comportamiento
  en caso de no-encontrado).

**¿Para qué NO sirve?**

- No prueba la lógica de negocio (validaciones, transformaciones).
- No prueba que los endpoints HTTP respondan con el código correcto.
- No detecta problemas de serialización JSON.
- No garantiza compatibilidad con PostgreSQL u otro motor de base de datos real
  (SQLite en memoria tiene diferencias sutiles).

---

### 1.2 `test_service.py` — Capa de lógica de negocio (BLL)

**¿Qué prueba?**
Llama a `TaskListService` y `TaskService` pasando una `session_factory` que crea una
base de datos SQLite en memoria. Verifica que los servicios apliquen las reglas de
negocio y devuelvan **diccionarios planos** (no objetos ORM).

**¿Qué cubre?**

- Que `create` devuelve un `dict` con los campos correctos.
- Que el estado por defecto de una tarea es `"pending"`.
- Que se puede crear una tarea con cualquiera de los cuatro estados válidos.
- Que un estado inválido lanza `ValueError`.
- Que `update` valida el nuevo estado antes de persistir.
- Que `delete` de una lista en cascada elimina sus tareas.
- Que filtrar tareas por `tasklist_id` inexistente devuelve lista vacía.

**¿Para qué sirve?**

- Verificar reglas de negocio sin involucrar HTTP ni serialización.
- Detectar regresiones cuando se cambia la lógica de validación.
- Servir de documentación ejecutable del comportamiento esperado del servicio.

**¿Para qué NO sirve?**

- No prueba la API HTTP ni los códigos de respuesta.
- No prueba que los errores se traduzcan correctamente a respuestas 400/422.
- No detecta problemas de integración con la base de datos real.

---

## 2. Pruebas funcionales de API — `tests/api/`

### 2.1 `test_flask_api.py` — API REST Flask

**¿Qué prueba?**
Usa el `test_client` integrado de Flask para enviar peticiones HTTP reales al prefijo
`/flask`. La base de datos es SQLite en memoria, creada fresca para cada prueba.

**¿Qué cubre?**

- Códigos de estado HTTP correctos (200, 201, 204, 400, 404, 415).
- Forma del cuerpo de la respuesta JSON (campos presentes, tipos).
- Comportamiento ante datos faltantes o inválidos (`name` ausente → 400).
- Filtrado por query param (`?tasklist_id=N`).
- Persistencia real: crea y luego consulta para confirmar que el dato se guardó.
- Cascada: borrar una lista elimina sus tareas.

**¿Para qué sirve?**

- Verificar que la capa HTTP (rutas, parseo de JSON, manejo de errores) funciona
  de extremo a extremo dentro del proceso.
- Detectar regresiones cuando se cambian los manejadores de ruta.
- Más rápido que levantar un servidor real pero más realista que las pruebas unitarias.

**¿Para qué NO sirve?**

- No prueba concurrencia ni rendimiento.
- No prueba comportamientos que dependan de la red real (timeouts, TLS).
- No verifica que el esquema OpenAPI (flasgger) esté alineado con lo que realmente
  devuelve la API — para eso existe Schemathesis.
- No descubre inputs inesperados que rompan el servidor.

---

### 2.2 `test_fastapi_api.py` — API REST FastAPI

**¿Qué prueba?**
Usa el `TestClient` de Starlette (respaldado por `httpx`) contra el prefijo `/fastapi`.

**¿Qué cubre?**
Los mismos escenarios que Flask con estas diferencias propias de FastAPI/Pydantic:

- Campos requeridos faltantes → `422` (validación Pydantic), no `400`.
- El campo `tasklist_id` ausente en la creación de tarea → `422`.
- Estado inválido → `400` (nuestro manejador de `ValueError`).

**¿Para qué sirve?** _(mismo propósito que Flask)_
Verificar la capa HTTP de FastAPI y detectar regresiones en los handlers.

**¿Para qué NO sirve?** _(mismas limitaciones que Flask)_

---

### 2.3 `test_graphql_api.py` — API GraphQL (Strawberry)

**¿Qué prueba?**
Envía peticiones `POST /graphql` con queries y mutations GraphQL usando el `test_client`
de Flask. Verifica tanto el camino feliz como los casos de no-encontrado.

**¿Qué cubre?**

- Todas las queries: `tasklists`, `tasklist(id)`, `tasks`, `tasks(tasklistId)`, `task(id)`.
- Todas las mutations: `createTasklist`, `deleteTasklist`, `createTask`, `updateTask`, `deleteTask`.
- Que errores de negocio se reflejan en el campo `errors` de GraphQL.
- Que `tasklist(id: 999)` devuelve `null` en `data` (no en `errors`), per spec GraphQL.
- Que los timestamps `createdAt` / `updatedAt` se incluyen correctamente.

**¿Para qué sirve?**
Verificar el comportamiento semántico de la API GraphQL (resolvers, tipos, nullable).

**¿Para qué NO sirve?**

- No valida la forma exacta del esquema GraphQL (para eso existe Schemathesis).
- No prueba fragmentos, subscriptions ni paginación.
- No detecta inputs arbitrarios que rompan el servidor.

---

### 2.4 `test_schemathesis.py` — Pruebas basadas en propiedades (Schemathesis)

**¿Qué prueba?**
Schemathesis lee el esquema OpenAPI de Flask y FastAPI y el esquema GraphQL de
Strawberry, luego **genera automáticamente cientos de inputs aleatorios** (valores límite,
tipos incorrectos, strings vacíos, enteros enormes, `null`) para cada operación y
verifica dos propiedades globales:

1. El servidor nunca devuelve un `5xx`.
2. Cada respuesta cumple el esquema declarado (tipos, campos, código de estado).

**¿Qué cubre?**

- Todos los endpoints de Flask REST (9 operaciones).
- Todos los endpoints de FastAPI REST (9 operaciones).
- Todas las queries y mutations GraphQL (9 operaciones).
- Casos de borde que un humano no pensaría probar (overflow de enteros, booleans
  donde se espera int, `"null"` como string en query params).

**¿Para qué sirve?**

- Encontrar bugs de robustez que las pruebas funcionales escritas a mano no detectan.
- Verificar que el esquema OpenAPI está alineado con el comportamiento real de la API.
- Descubrir que la API acepta inputs inválidos sin devolver 4xx (falso positivo del lado
  del servidor).

**¿Para qué NO sirve?**

- No prueba lógica de negocio ni semántica (que el dato devuelto sea correcto).
- No reemplaza las pruebas funcionales: Schemathesis no sabe si el resultado tiene
  sentido, solo si cumple el esquema.

---

## 3. Pruebas de contrato (CDCT) — `tests/pact/`

### 3.1 `test_flask_pact.py` y `test_fastapi_pact.py`

**¿Qué prueba?**
Consumer-Driven Contract Testing (CDCT) con la librería Pact.
Cada archivo tiene dos fases:

| Fase       | Clase                                       | Qué hace                                                                                                                               |
| ---------- | ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Consumidor | `TestFlaskConsumer` / `TestFastAPIConsumer` | El consumidor llama a un mock del proveedor y graba las interacciones en un archivo JSON (el contrato).                                |
| Proveedor  | `TestFlaskProvider` / `TestFastAPIProvider` | El proveedor real se levanta y se verifica contra el contrato grabado. Si alguna interacción falla, el proveedor no puede desplegarse. |

**¿Qué cubre?**

- Que el proveedor devuelve los campos que el consumidor declaró necesitar.
- Que los tipos de datos son correctos (entero, string, lista).
- Que los códigos de estado HTTP son los esperados.
- Que agregar un campo obligatorio al request rompe el contrato (detectado → fallo).
- Que renombrar un campo en la respuesta rompe el contrato (detectado → fallo).

**¿Para qué sirve?**

- Garantizar que cambios en el proveedor no rompen a los consumidores existentes,
  sin necesidad de tests de integración end-to-end.
- Definir quién es responsable de qué: el consumidor dicta sus necesidades, el
  proveedor reacciona.
- Coordinar despliegues independientes de servicios en una arquitectura de microservicios.

**¿Para qué NO sirve?**

- No detecta campos extra que el proveedor agrega a la respuesta (Pact los ignora
  intencionalmente — son compatibles hacia atrás).
- No prueba lógica de negocio ni reglas de dominio.
- No prueba endpoints que el consumidor no haya declarado en el contrato.
- No reemplaza pruebas de integración completas (autenticación real, base de datos
  compartida, flujos multi-paso).

---

## Resumen comparativo

| Criterio                          | Unit (repo/svc)  | API funcional | Schemathesis  | Pact                |
| --------------------------------- | ---------------- | ------------- | ------------- | ------------------- |
| **Velocidad**                     | ⚡ Muy rápido    | 🟢 Rápido     | 🟡 Medio      | 🔴 Lento            |
| **Aislamiento**                   | Total (sin HTTP) | Proceso único | Proceso único | Dos procesos        |
| **¿Prueba HTTP?**                 | No               | Sí            | Sí            | Sí                  |
| **¿Prueba lógica de negocio?**    | Sí               | Parcial       | No            | No                  |
| **¿Detecta inputs inesperados?**  | No               | No            | Sí            | No                  |
| **¿Detecta cambios de contrato?** | No               | No            | Parcial       | Sí                  |
| **¿Necesita servidor real?**      | No               | No            | No            | Sí (fase proveedor) |
| **¿Quién escribe los casos?**     | Humano           | Humano        | Automático    | Humano (consumidor) |

---

## ¿Cuándo falla cada tipo?

```
cambio en la BD / ORM          →  unit/test_repository.py lo detecta
cambio en regla de negocio     →  unit/test_service.py lo detecta
cambio en un endpoint HTTP     →  api/test_flask_api.py / test_fastapi_api.py / test_graphql_api.py
API acepta input inválido      →  api/test_schemathesis.py lo detecta
proveedor rompe al consumidor  →  pact/test_flask_pact.py / test_fastapi_pact.py lo detecta
```

Ninguna categoría reemplaza a las demás — son capas complementarias de confianza.
