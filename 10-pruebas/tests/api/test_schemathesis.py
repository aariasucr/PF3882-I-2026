"""
Pruebas de API basadas en propiedades con Schemathesis.

Para cada operación descubierta, schemathesis genera entradas aleatorias válidas
(cadenas, enteros, valores límite) y verifica que el servidor nunca retorne una
respuesta 5xx y que cada respuesta cumpla con el esquema declarado.

Flask OpenAPI   — 9 operaciones vía spec de flasgger (/flask/apispec.json)
FastAPI OpenAPI — 9 operaciones vía spec integrado (/fastapi/openapi.json)
GraphQL         — schemathesis introspecta el esquema de Strawberry y genera
                  queries y mutations aleatorias válidas contra /graphql

El patrón de fixture lazy (schemathesis.pytest.from_fixture) permite que cada
función de prueba reciba una base de datos SQLite nueva a través del fixture
session_factory, manteniendo las pruebas completamente aisladas sin requerir
PostgreSQL.

──────────────────────────────────────────────────────────────────────────────
FALLOS CONOCIDOS (dejados intencionalmente sin resolver — corregir en clase)
──────────────────────────────────────────────────────────────────────────────

1. DESBORDAMIENTO DE ENTERO → 500
   ─────────────────────────────────
   Schemathesis genera enteros Python de precisión arbitraria (por ejemplo,
   id=99999999999999999999 como parámetro de ruta). El tipo INTEGER de SQLite
   tiene un límite de 64 bits con signo, por lo que SQLAlchemy lanza
   OverflowError, que Flask/FastAPI convierte en un 500.

   Reproducción:
       curl -X GET /flask/tasklists/99999999999999999999

   Opciones de corrección (elegir una):
   a) Agregar límites a todos los parámetros enteros en los specs OpenAPI:
      - docstrings de flasgger: agregar `minimum: 1` y `maximum: 2147483647`
      - FastAPI: usar `id: int = Path(ge=1, le=2147483647)`
   b) Capturar OverflowError en el repositorio/servicio y lanzar ValueError
      que las capas de API traduzcan a 400/422.
   c) Configurar schemathesis para usar generación de enteros acotada:
          from schemathesis import GenerationMode
          @_flask.parametrize(generation_modes=[GenerationMode.POSITIVE])
      (esto limita la generación a datos válidos según el esquema, sin extremos)

2. PARÁMETRO QUERY NULL ACEPTADO → fallo de conformidad con esquema (solo Flask)
   ──────────────────────────────────────────────────────────────────────────────
   Schemathesis envía `GET /flask/tasks?tasklist_id=null` para verificar que la
   API rechace valores que no son enteros. El método
   `request.args.get("tasklist_id", type=int)` de Flask retorna None
   silenciosamente cuando el valor no se puede parsear como int, por lo que el
   endpoint retorna 200 [] en vez del 4xx esperado.

   El esquema OpenAPI declara `tasklist_id` como tipo integer, por lo que
   schemathesis marca correctamente esto como "API aceptó petición que viola
   el esquema".

   Opciones de corrección (elegir una):
   a) Agregar validación explícita de tipo en el manejador de ruta Flask:
          raw = request.args.get("tasklist_id")
          if raw is not None:
              try:
                  tasklist_id = int(raw)
              except ValueError:
                  return jsonify({"error": "tasklist_id must be an integer"}), 400
   b) Marcar el parámetro query como opcional sin restricción de tipo en el spec,
      para que schemathesis sepa que cualquier valor es aceptable.
   c) Usar una librería de parseo de requests Flask (por ejemplo, webargs) que
      aplique automáticamente los tipos declarados en el esquema.

3. OPERACIONES GraphQL FALLIDAS
   ──────────────────────────────
   Algunas mutations generadas (por ejemplo, createTask con un tasklistId muy
   grande) provocan el mismo desbordamiento de entero que el problema #1,
   retornando 500. Las mismas correcciones del problema #1 aplican aquí.
──────────────────────────────────────────────────────────────────────────────
"""
import schemathesis.pytest as st_pytest

# ── Flask REST ────────────────────────────────────────────────────────────────
# Resuelve el fixture flask_schema definido en tests/api/conftest.py

_flask = st_pytest.from_fixture("flask_schema")


@_flask.parametrize()
def test_flask_openapi(case):
    """
    Para cada endpoint Flask + entradas aleatorias: sin 5xx, respuesta cumple esquema.
    Cubre: GET /flask/tasklists, POST /flask/tasklists,
            GET/DELETE /flask/tasklists/{id},
            GET /flask/tasks, POST /flask/tasks,
            GET/PUT/DELETE /flask/tasks/{id}

    FALLA ACTUALMENTE — ver docstring del módulo para causas raíz y correcciones.
    """
    case.call_and_validate()


# ── FastAPI REST ──────────────────────────────────────────────────────────────
# Resuelve el fixture fastapi_schema definido en tests/api/conftest.py

_fastapi = st_pytest.from_fixture("fastapi_schema")


@_fastapi.parametrize()
def test_fastapi_openapi(case):
    """
    Para cada endpoint FastAPI + entradas aleatorias: sin 5xx, respuesta cumple esquema.
    Cubre las mismas 9 operaciones que Flask pero vía transporte ASGI.

    FALLA ACTUALMENTE — ver docstring del módulo para causas raíz y correcciones.
    """
    case.call_and_validate()


# ── GraphQL ───────────────────────────────────────────────────────────────────
# Schemathesis introspecta el esquema Strawberry vía la query estándar de
# introspección GraphQL, luego genera queries y mutations aleatorias válidas.
# Resuelve el fixture graphql_schema definido en tests/api/conftest.py

_graphql = st_pytest.from_fixture("graphql_schema")


@_graphql.parametrize()
def test_graphql_schema(case):
    """
    Para cada operación GraphQL + entradas aleatorias: sin 5xx, respuesta es JSON
    válido con clave 'data' o 'errors' (cumplimiento de spec GraphQL).
    Cubre: queries tasklists, tasklist, tasks, task +
            mutations createTasklist, deleteTasklist, createTask, updateTask, deleteTask.

    FALLA ACTUALMENTE — ver docstring del módulo para causas raíz y correcciones.
    """
    case.call_and_validate()
