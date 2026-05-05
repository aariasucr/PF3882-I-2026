"""
Pruebas de Contrato Dirigidas por el Consumidor (Consumer-Driven Contract Testing)
para la API REST FastAPI usando pact-python v3.

═══════════════════════════════════════════════════════════════════════════════
¿EN QUÉ SE DIFERENCIA ESTE ARCHIVO DEL DE FLASK?
═══════════════════════════════════════════════════════════════════════════════

La lógica de negocio es idéntica. Las diferencias son técnicas:

  1. Formato de respuestas de error:
       Flask  → {"error": "not found"}      (definido en el código Python)
       FastAPI → {"detail": "not found"}    (formato estándar de HTTPException)

     Cada consumidor debe tener su propio contrato porque negocia con
     su proveedor específico. Un consumidor de Flask no puede usar el
     contrato de FastAPI y viceversa.

  2. Servidor del proveedor:
       Flask  → werkzeug (make_server), ligero, síncrono
       FastAPI → uvicorn (ASGI), asíncrono, requiere manejo de señales

  3. URL del proveedor:
       Verifier() por defecto usa host="localhost".
       El servidor FastAPI debe levantarse en "localhost" (no "127.0.0.1")
       porque pact-python v3 valida que el host del Verifier y el de la
       URL de add_transport() coincidan exactamente.

═══════════════════════════════════════════════════════════════════════════════
FLUJO COMPLETO DE EJECUCIÓN
═══════════════════════════════════════════════════════════════════════════════

  1. pytest importa el módulo → el objeto pact = Pact(...) se crea.

  2. La fixture pact_mock (scope="module") se activa:
       a. Se registran las 4 interacciones en el objeto pact.
       b. pact.serve() arranca el mock en MOCK_PORT.
       c. mock.write_file() escribe el contrato JSON en disco.
       d. yield → los tests del módulo pueden correr.

  3. TestFastAPIConsumer (4 tests):
       Cada test envía una petición al mock y verifica la respuesta.
       El mock no usa base de datos; responde según lo configurado.

  4. TestFastAPIProvider (1 test):
       Levanta uvicorn con la app FastAPI real (base de datos en memoria).
       Verifier lee el contrato JSON y reproduce las 4 interacciones.
       Compara las respuestas reales con las del contrato.

  5. La fixture pact_mock sale del bloque "with" → el mock se detiene.
"""
import pathlib
import threading
import time

import pytest
import requests
import uvicorn
from pact import Pact, Verifier, match
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base

# ── Constantes de configuración ───────────────────────────────────────────────

# Raíz del proyecto calculada desde la ubicación de este archivo.
# tests/pact/test_fastapi_pact.py → parents[2] = 09-pruebas/
_PROJECT_ROOT = pathlib.Path(__file__).parents[2]

# Directorio absoluto donde se guardan los contratos Pact.
# Usar ruta absoluta evita problemas con el directorio de trabajo de pytest.
PACT_DIR = str(_PROJECT_ROOT / "pacts")

# Puerto del servidor mock (simula a FastAPI durante las pruebas del consumidor).
MOCK_PORT = 5202

# Puerto del servidor FastAPI real (durante la verificación del proveedor).
# Usamos puertos distintos a los de Flask (5200/5201) para evitar conflictos
# si ambos test files se ejecutan en la misma sesión de pytest.
PROVIDER_PORT = 5203

# Ruta al archivo de contrato que generará el consumidor y leerá el proveedor.
# Pact nombra el archivo automáticamente: "<consumidor>-<proveedor>.json"
PACT_FILE = str(_PROJECT_ROOT / "pacts" / "TasklistClient-FastAPITasklistAPI.json")

# ── Creación del objeto Pact ───────────────────────────────────────────────────

# Pact("consumidor", "proveedor") es el punto de entrada principal en v3.
# Acumula las interacciones que se le registran y las usa para:
#   a) configurar el servidor mock (Fase 1)
#   b) generar el archivo JSON del contrato
pact = Pact("TasklistClient", "FastAPITasklistAPI")


# ── Fixture del mock (módulo completo) ────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def pact_mock():
    """
    Fixture de módulo que gestiona el ciclo de vida completo del mock de Pact:
    registro de interacciones → arranque del mock → escritura del contrato → tests.

    Por qué scope="module":
      Levantar y detener el mock tiene costo. Con scope="module" el mock vive
      durante todo el módulo en lugar de reiniciarse por cada test.

    Por qué autouse=True:
      El mock debe estar corriendo antes de cualquier test del módulo,
      incluyendo los de la Fase 2 (proveedor), que necesitan el contrato escrito.
      Con autouse la fixture se activa sin que cada test la declare explícitamente.
    """

    # ══════════════════════════════════════════════════════════════════════════
    # REGISTRO DE INTERACCIONES
    # ══════════════════════════════════════════════════════════════════════════
    #
    # Cada llamada a pact.upon_receiving() define UNA interacción del contrato.
    # Una interacción tiene tres partes:
    #   - Estado previo (.given)        : qué debe ser verdad en el proveedor
    #   - Petición (.with_request)      : qué envía el consumidor
    #   - Respuesta (.will_respond_with): qué espera recibir el consumidor
    #
    # Los MATCHERS (match.integer, match.string, match.each_like) permiten
    # verificar TIPOS y ESTRUCTURA sin requerir valores exactos.
    # Esto hace los contratos más robustos: el proveedor puede cambiar el
    # valor de "name" siempre que siga siendo un string.
    # ══════════════════════════════════════════════════════════════════════════

    # ── Interacción 1: Listar todas las listas de tareas ─────────────────────
    #
    # match.each_like({...}):
    #   La respuesta es un ARRAY. Cada elemento debe tener la misma estructura
    #   que el objeto de ejemplo. Pact verifica que el array no esté vacío y
    #   que todos los elementos cumplan la estructura.
    #
    # match.integer(1):
    #   "id" debe ser un número entero. El 1 es un valor de ejemplo usado
    #   en el mock (la respuesta del mock tendrá id=1).
    #
    # match.string("Shopping"):
    #   "name" debe ser un string. "Shopping" es el valor de ejemplo del mock.
    (
        pact.upon_receiving("GET /fastapi/tasklists returns a list")
        .given("at least one tasklist exists")
        .with_request("GET", "/fastapi/tasklists")
        .will_respond_with(200)
        .with_body(
            match.each_like({"id": match.integer(1), "name": match.string("Shopping"), "tasks": []}),
            content_type="application/json",
        )
        .with_header("Content-Type", "application/json")
    )

    # ── Interacción 2: Crear una nueva lista ─────────────────────────────────
    #
    # Esta interacción tiene cuerpo en la PETICIÓN y en la RESPUESTA.
    #
    # Regla de pact-python v3:
    #   .with_body() antes de .will_respond_with() → aplica al REQUEST
    #   .with_body() después de .will_respond_with() → aplica al RESPONSE
    #
    # El body del request es un valor exacto ({"name": "Shopping"}) porque
    # el consumidor sabe exactamente qué enviará.
    # El body del response usa match.integer(1) para el id porque el proveedor
    # asigna el id y el consumidor no sabe qué valor tendrá.
    (
        pact.upon_receiving("POST /fastapi/tasklists creates a new tasklist")
        .given("any state")
        .with_request("POST", "/fastapi/tasklists")
        .with_body({"name": "Shopping"}, content_type="application/json")  # ← request body
        .will_respond_with(201)
        .with_body(                                                          # ← response body
            {"id": match.integer(1), "name": "Shopping", "tasks": []},
            content_type="application/json",
        )
        .with_header("Content-Type", "application/json")
    )

    # ── Interacción 3: Obtener una lista específica por ID ───────────────────
    #
    # El id=1 en el body de la respuesta es un valor EXACTO (no un matcher).
    # El consumidor verifica que el servidor devuelva la misma lista que pidió.
    # El name usa match.string() porque el nombre puede cambiar.
    (
        pact.upon_receiving("GET /fastapi/tasklists/1 returns the tasklist")
        .given("a tasklist with id 1 exists")
        .with_request("GET", "/fastapi/tasklists/1")
        .will_respond_with(200)
        .with_body(
            {"id": 1, "name": match.string("Shopping"), "tasks": []},
            content_type="application/json",
        )
        .with_header("Content-Type", "application/json")
    )

    # ── Interacción 4: Recurso no encontrado (404) ───────────────────────────
    #
    # DIFERENCIA CLAVE con Flask:
    #   FastAPI serializa HTTPException como {"detail": "mensaje"}
    #   Flask devuelve     {"error": "mensaje"}
    #
    # Esto ilustra por qué cada consumidor necesita su propio contrato:
    # el formato de error es parte del "acuerdo" con ese proveedor específico.
    (
        pact.upon_receiving("GET /fastapi/tasklists/999 returns 404")
        .given("no tasklist with id 999 exists")
        .with_request("GET", "/fastapi/tasklists/999")
        .will_respond_with(404)
        .with_body(
            {"detail": match.string("not found")},   # FastAPI usa "detail", no "error"
            content_type="application/json",
        )
        .with_header("Content-Type", "application/json")
    )

    # ══════════════════════════════════════════════════════════════════════════
    # ARRANQUE DEL SERVIDOR MOCK
    # ══════════════════════════════════════════════════════════════════════════
    #
    # pact.serve() levanta un servidor HTTP que conoce las 4 interacciones
    # registradas. Cuando recibe una petición:
    #   1. Busca una interacción cuya "with_request" coincida.
    #   2. Si la encuentra, devuelve la respuesta configurada.
    #   3. Si no la encuentra, devuelve 500 (con raises=False no lanza excepción).
    #
    # mock.url → la URL base del mock, ej: "http://localhost:5202"
    # mock.matched → True si TODAS las interacciones registradas fueron llamadas
    # mock.mismatches → lista de diferencias cuando algo no coincide
    # ══════════════════════════════════════════════════════════════════════════
    with pact.serve(port=MOCK_PORT, raises=False) as mock:

        # ── Escritura anticipada del contrato ─────────────────────────────
        #
        # Escribimos el archivo de contrato DENTRO del bloque "with" (el mock
        # debe estar corriendo para que write_file() funcione) pero ANTES del
        # yield (antes de que corran los tests).
        #
        # Por qué antes del yield:
        #   TestFastAPIProvider corre en el mismo módulo que TestFastAPIConsumer.
        #   La fixture de módulo envuelve TODOS los tests del módulo.
        #   Si escribiéramos después del yield, el proveedor intentaría leer
        #   el contrato durante su test, pero el yield aún no habría retornado
        #   y write_file() no habría corrido → FileNotFoundError.
        #
        # overwrite=True → permite re-ejecutar los tests sin limpiar manualmente.
        mock.write_file(PACT_DIR, overwrite=True)

        # yield transfiere el control a los tests. La variable "mock" estará
        # disponible como parámetro de fixture en los tests que la soliciten.
        yield mock

    # Al salir del "with", el servidor mock se detiene automáticamente.


# ── Fase 1: Pruebas del Consumidor ────────────────────────────────────────────

class TestFastAPIConsumer:
    """
    Pruebas del CONSUMIDOR: verifican que el cliente HTTP sabe comunicarse
    con la API FastAPI según el contrato definido.

    Estas pruebas NO ejecutan código de FastAPI. Todo va al mock.
    Su propósito es triple:
      1. Documentar lo que el consumidor espera del proveedor.
      2. Generar el archivo de contrato (.json).
      3. Verificar que el consumidor puede procesar las respuestas correctamente.

    Si el consumidor cambia cómo llama a la API (distinto método, path, body),
    estos tests fallarán → hay que actualizar el contrato y coordinar con el
    equipo del proveedor.
    """

    def test_list_tasklists(self, pact_mock):
        # pact_mock.url es "http://localhost:5202" (el servidor mock).
        # El mock devuelve la respuesta configurada en la Interacción 1.
        r = requests.get(f"{pact_mock.url}/fastapi/tasklists")

        assert r.status_code == 200
        # El consumidor sabe que la respuesta es una lista (array JSON).
        assert isinstance(r.json(), list)

    def test_create_tasklist(self, pact_mock):
        # json={"name": "Shopping"} → requests serializa automáticamente a JSON
        # y añade Content-Type: application/json.
        r = requests.post(
            f"{pact_mock.url}/fastapi/tasklists",
            json={"name": "Shopping"},
        )
        assert r.status_code == 201
        # El consumidor verifica que el proveedor devuelve el nombre tal como fue enviado.
        assert r.json()["name"] == "Shopping"

    def test_get_tasklist_by_id(self, pact_mock):
        r = requests.get(f"{pact_mock.url}/fastapi/tasklists/1")
        assert r.status_code == 200
        # El consumidor verifica que el id en la respuesta coincide con el solicitado.
        assert r.json()["id"] == 1

    def test_get_tasklist_not_found(self, pact_mock):
        r = requests.get(f"{pact_mock.url}/fastapi/tasklists/999")
        # El consumidor debe poder manejar respuestas 404 sin crashear.
        assert r.status_code == 404


# ── Fase 2: Verificación del Proveedor ───────────────────────────────────────

class _UvicornServer(uvicorn.Server):
    """
    Subclase de uvicorn.Server que deshabilita el manejo de señales del SO.

    Por qué es necesaria:
      uvicorn normalmente captura SIGINT y SIGTERM para detenerse limpiamente.
      En un hilo (Thread), estas señales no se pueden manejar correctamente
      porque Python solo procesa señales en el hilo principal.
      Al sobreescribir install_signal_handlers() con pass, evitamos el error
      "signal only works in main thread" cuando corremos uvicorn en background.

    Para detener el servidor usamos server.should_exit = True en el teardown.
    """

    def install_signal_handlers(self) -> None:
        pass


@pytest.fixture(scope="class")
def fastapi_provider_url():
    """
    Fixture que levanta la app FastAPI REAL con SQLite en memoria para que
    el verificador de Pact pueda hacer peticiones HTTP reales.

    scope="class" → la app se crea una vez para toda la clase TestFastAPIProvider.
    Si hubiera múltiples tests en la clase, compartirían el mismo servidor.

    Arquitectura del setup:
      pytest process
        └── main thread (pytest)
              └── background thread → uvicorn server → FastAPI app → SQLite in-memory
    """
    # SQLite en memoria con StaticPool:
    #   - "sqlite:///:memory:" → BD en RAM, se destruye al cerrar la conexión.
    #   - check_same_thread=False → permite acceso desde múltiples threads
    #     (uvicorn maneja workers en threads).
    #   - StaticPool → todos los threads comparten UNA sola conexión.
    #     Sin esto, cada thread vería una BD diferente (vacía).
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Crea las tablas según los modelos SQLAlchemy (TaskList, Task).
    Base.metadata.create_all(engine)

    # sessionmaker crea una "fábrica" de sesiones SQLAlchemy.
    # expire_on_commit=False → los objetos siguen accesibles después de commit.
    sf = sessionmaker(bind=engine, expire_on_commit=False)

    from app import fastapi_api
    from app.service import TaskListService, TaskService

    # Inyección de dependencias manual:
    # Reemplazamos las instancias globales del módulo fastapi_api por instancias
    # que usan nuestra BD de prueba en lugar de la BD de producción.
    # Esto evita contaminar datos reales y permite pruebas aisladas.
    fastapi_api.tasklist_service = TaskListService(session_factory=sf)
    fastapi_api.task_service = TaskService(session_factory=sf)

    # Datos de prueba para satisfacer los estados del contrato:
    #   "at least one tasklist exists"    → creamos "Shopping" (id=1)
    #   "a tasklist with id 1 exists"     → misma lista
    #   "no tasklist with id 999 exists"  → ninguna fila tiene id=999 (automático)
    fastapi_api.tasklist_service.create("Shopping")

    # Creamos la app FastAPI con todos sus endpoints configurados.
    app = fastapi_api.create_fastapi_app()

    # Configuración de uvicorn:
    #   host="localhost" → OBLIGATORIO para que coincida con el host del Verifier.
    #     pact-python v3 valida que Verifier(host) == add_transport(url.host).
    #     Si usáramos "127.0.0.1", el Verifier daría ValueError: Host mismatch.
    #   log_level="error" → silenciamos los logs de acceso para no saturar la salida.
    config = uvicorn.Config(app, host="localhost", port=PROVIDER_PORT, log_level="error")
    server = _UvicornServer(config)

    # Hilo daemon: si pytest muere, el hilo también muere (no queda colgado).
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    # Esperamos a que uvicorn esté listo para recibir peticiones.
    # 0.5s es suficiente en la mayoría de sistemas. En CI lento podría ser más.
    time.sleep(0.5)

    yield f"http://localhost:{PROVIDER_PORT}"

    # Teardown: señalamos a uvicorn que debe detenerse en su próximo ciclo.
    server.should_exit = True
    t.join(timeout=2)  # esperamos máximo 2 segundos a que el hilo termine


class TestFastAPIProvider:
    """
    Verifica que la app FastAPI REAL cumple el contrato generado por el consumidor.

    El Pact Verifier:
      1. Lee el archivo JSON del contrato (PACT_FILE).
      2. Para cada interacción:
           a. Reproduce la petición contra el proveedor real.
           b. Compara la respuesta (status code, headers, body) con el contrato.
           c. Los matchers del contrato se evalúan (ej: verifica que "id" es int).
      3. Reporta cuántas interacciones fallaron.

    Si el proveedor pasa este test, significa que puede satisfacer al consumidor
    tal como fue negociado en el contrato.
    """

    def test_provider_honours_pact(self, fastapi_provider_url):
        # Verifier("FastAPITasklistAPI"):
        #   El nombre debe ser EXACTAMENTE el mismo que el usado en
        #   Pact("TasklistClient", "FastAPITasklistAPI"). Pact usa este nombre
        #   para filtrar qué interacciones del contrato le corresponden a este proveedor.
        #
        # .add_transport(url=fastapi_provider_url):
        #   Indica la URL base donde está corriendo el proveedor real.
        #   Pact hará peticiones a esta URL + el path de cada interacción.
        #   Ej: http://localhost:5203 + /fastapi/tasklists → GET http://localhost:5203/fastapi/tasklists
        #
        # .add_source(PACT_FILE):
        #   Especifica qué contrato verificar. Puede ser:
        #   - Ruta a un archivo .json específico (nuestro caso)
        #   - Ruta a un directorio (verifica todos los .json del directorio)
        #   - URL a un Pact Broker (servicio centralizado de contratos)
        #
        # .verify():
        #   Ejecuta la verificación. Internamente usa la librería Rust (pact-ffi)
        #   para máximo rendimiento y compatibilidad con la especificación Pact v4.
        verifier = (
            Verifier("FastAPITasklistAPI")
            .add_transport(url=fastapi_provider_url)
            .add_source(PACT_FILE)
        )
        verifier.verify()

        # verifier.results contiene el resumen detallado de la verificación.
        # Ejemplo de estructura:
        #   {
        #     "summary": {"testCount": 4, "failureCount": 0, "pendingCount": 0},
        #     "testResults": [
        #       {"interactionId": "...", "description": "GET /fastapi/tasklists...", "success": true},
        #       ...
        #     ]
        #   }
        results = verifier.results
        failures = results.get("summary", {}).get("failureCount", 0)

        # Assertion explícita con mensaje descriptivo:
        # Si falla, el mensaje muestra el dict completo para saber qué interacción
        # no cumplió el contrato y por qué.
        assert failures == 0, f"El proveedor FastAPI no satisfizo {failures} interacción(es): {results}"
