"""
Pruebas de Contrato Dirigidas por el Consumidor (Consumer-Driven Contract Testing)
para la API REST Flask usando pact-python v3.

═══════════════════════════════════════════════════════════════════════════════
¿QUÉ ES CONTRACT TESTING?
═══════════════════════════════════════════════════════════════════════════════

En arquitecturas de microservicios, un CONSUMIDOR es el servicio que hace
peticiones HTTP, y un PROVEEDOR es el servicio que las responde.

El problema: si el proveedor cambia su API sin avisar, el consumidor se rompe.
Los tests de integración clásicos requieren tener ambos servicios corriendo.

Contract Testing resuelve esto en DOS FASES independientes:

  Fase 1 — Pruebas del Consumidor (offline):
    El consumidor define exactamente qué peticiones hará y qué respuestas
    espera. pact-python levanta un servidor mock que simula al proveedor y
    graba esas expectativas en un archivo JSON llamado "contrato" (pact file).
    El proveedor NO necesita estar corriendo.

  Fase 2 — Verificación del Proveedor (online):
    El proveedor real arranca y el verificador de Pact reproduce cada
    interacción del contrato contra él. Si el proveedor responde de forma
    diferente a lo esperado, la verificación falla.

Ventaja clave: cada servicio se puede probar de forma independiente.
El contrato es el "acuerdo" entre ambos equipos.

═══════════════════════════════════════════════════════════════════════════════
PACT-PYTHON V3 VS V2
═══════════════════════════════════════════════════════════════════════════════

  v2 (API antigua, ya no disponible):
    from pact import Consumer, Provider, Like
    pact = Consumer("A").has_pact_with(Provider("B"), host_name="localhost", port=...)
    pact.start_service()   # proceso externo (Ruby standalone)
    pact.stop_service()
    pact.verify()          # comprobación por interacción

  v3 (API actual, basada en Rust FFI):
    from pact import Pact, Verifier, match
    pact = Pact("A", "B")
    with pact.serve(port=...) as mock:   # context manager, sin proceso externo
        mock.write_file(directorio)       # escribe el contrato en JSON
        ...
    verifier = Verifier("B").add_transport(url=...).add_source(archivo).verify()

  Cambios principales:
    - Consumer/Provider              →  Pact("consumidor", "proveedor")
    - Like(x)                        →  match.like(x)
    - start_service()/stop_service() →  with pact.serve() as mock:
    - pact.verify()                  →  assert mock.matched  (o verifier.results)
    - El contrato se escribe con     →  mock.write_file()
"""
import pathlib
import threading
import time

import pytest
import requests
from pact import Pact, Verifier, match
from werkzeug.serving import make_server
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base

# ── Constantes de configuración ───────────────────────────────────────────────

# Calculamos la raíz del proyecto a partir de la ubicación de este archivo.
# __file__ es tests/pact/test_flask_pact.py
# .parents[0] = tests/pact/
# .parents[1] = tests/
# .parents[2] = 09-pruebas/   ← raíz del proyecto
_PROJECT_ROOT = pathlib.Path(__file__).parents[2]

# Directorio donde se guardarán los archivos de contrato (.json).
# Usamos ruta absoluta para que tanto mock.write_file() como Verifier.add_source()
# encuentren el archivo independientemente del directorio de trabajo.
PACT_DIR = str(_PROJECT_ROOT / "pacts")

# Puerto donde correrá el servidor mock de Pact durante las pruebas del consumidor.
MOCK_PORT = 5200

# Puerto donde correrá la app Flask real durante la verificación del proveedor.
PROVIDER_PORT = 5201

# Ruta completa al archivo de contrato que se generará y luego se leerá.
# El nombre lo determina Pact automáticamente: "<consumidor>-<proveedor>.json"
PACT_FILE = str(_PROJECT_ROOT / "pacts" / "TasklistClient-FlaskTasklistAPI.json")

# ── Creación del objeto Pact ───────────────────────────────────────────────────

# Pact("consumidor", "proveedor") crea el objeto que acumula las interacciones.
# "TasklistClient" es el nombre del servicio consumidor (el cliente HTTP).
# "FlaskTasklistAPI" es el nombre del servicio proveedor (la API Flask).
# Estos nombres se usan para nombrar el archivo JSON del contrato.
pact = Pact("TasklistClient", "FlaskTasklistAPI")


# ── Fixture del mock (módulo completo) ────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def pact_mock():
    """
    Fixture de módulo que:
      1. Registra las cuatro interacciones en el objeto pact.
      2. Levanta el servidor mock de Pact en MOCK_PORT.
      3. Escribe el archivo de contrato ANTES de que los tests corran.
      4. Cede el control a los tests del módulo (consumidor y proveedor).
      5. Al finalizar, el context manager cierra el mock automáticamente.

    scope="module"  → la fixture se crea una vez por módulo (no por test).
    autouse=True    → se aplica automáticamente a todos los tests del módulo
                      sin necesidad de declararla como parámetro.
    """

    # ── Interacción 1: GET /flask/tasklists ───────────────────────────────────
    #
    # El consumidor dice: "cuando envíe GET /flask/tasklists,
    # dado que existe al menos una lista, espero recibir un array JSON con
    # objetos que tengan id (entero), name (string) y tasks (array vacío)."
    #
    # match.each_like({...}):
    #   Indica que la respuesta es un ARRAY donde cada elemento tiene
    #   la misma estructura que el objeto de ejemplo. No verifica valores
    #   exactos, solo tipos y estructura.
    #
    # match.integer(1):
    #   El campo "id" debe ser un entero. El valor 1 es solo un ejemplo.
    #
    # match.string("Shopping"):
    #   El campo "name" debe ser un string. "Shopping" es solo un ejemplo.
    (
        pact.upon_receiving("GET /flask/tasklists returns a list")
        .given("at least one tasklist exists")        # estado previo del proveedor
        .with_request("GET", "/flask/tasklists")      # método y ruta de la petición
        .will_respond_with(200)                        # código de estado esperado
        .with_body(
            match.each_like({"id": match.integer(1), "name": match.string("Shopping"), "tasks": []}),
            content_type="application/json",
        )
        .with_header("Content-Type", "application/json")
    )

    # ── Interacción 2: POST /flask/tasklists ──────────────────────────────────
    #
    # El consumidor dice: "cuando envíe POST con body {"name": "Shopping"},
    # espero un 201 con el objeto creado (id flexible, name exacto)."
    #
    # Nota: .with_body() ANTES de .will_respond_with() → aplica al REQUEST.
    #       .with_body() DESPUÉS de .will_respond_with() → aplica al RESPONSE.
    (
        pact.upon_receiving("POST /flask/tasklists creates a new tasklist")
        .given("any state")
        .with_request("POST", "/flask/tasklists")
        .with_body({"name": "Shopping"}, content_type="application/json")  # body del request
        .will_respond_with(201)
        .with_body(                                                          # body del response
            {"id": match.integer(1), "name": "Shopping", "tasks": []},
            content_type="application/json",
        )
        .with_header("Content-Type", "application/json")
    )

    # ── Interacción 3: GET /flask/tasklists/1 ────────────────────────────────
    #
    # Busca un recurso específico por ID. El id=1 en el body es exacto
    # (el cliente verifica que el id devuelto sea el mismo que pidió),
    # pero el name es flexible (match.string).
    (
        pact.upon_receiving("GET /flask/tasklists/1 returns the tasklist")
        .given("a tasklist with id 1 exists")
        .with_request("GET", "/flask/tasklists/1")
        .will_respond_with(200)
        .with_body(
            {"id": 1, "name": match.string("Shopping"), "tasks": []},
            content_type="application/json",
        )
        .with_header("Content-Type", "application/json")
    )

    # ── Interacción 4: GET /flask/tasklists/999 (404) ─────────────────────────
    #
    # Flask usa {"error": "..."} para errores (a diferencia de FastAPI que
    # usa {"detail": "..."}). El contrato documenta exactamente este formato.
    # match.string("not found") → el mensaje puede ser cualquier string.
    (
        pact.upon_receiving("GET /flask/tasklists/999 returns 404")
        .given("no tasklist with id 999 exists")
        .with_request("GET", "/flask/tasklists/999")
        .will_respond_with(404)
        .with_body(
            {"error": match.string("not found")},
            content_type="application/json",
        )
        .with_header("Content-Type", "application/json")
    )

    # ── Arranque del servidor mock ────────────────────────────────────────────
    #
    # pact.serve() es un context manager que:
    #   - Levanta un servidor HTTP en MOCK_PORT que conoce las 4 interacciones.
    #   - Cuando recibe una petición, busca la interacción coincidente y
    #     devuelve la respuesta configurada (sin tocar ninguna base de datos).
    #   - Al salir del bloque "with", detiene el servidor automáticamente.
    #
    # raises=False → si una petición no coincide con ninguna interacción,
    #   devuelve error 500 pero NO lanza excepción en Python. Esto permite
    #   que los tests fallen con assert en vez de con una excepción inesperada.
    with pact.serve(port=MOCK_PORT, raises=False) as mock:

        # ── Escritura del contrato ─────────────────────────────────────────
        #
        # IMPORTANTE: escribimos el archivo ANTES del yield (antes de que
        # corran los tests) porque el TestFlaskProvider que está en este
        # mismo módulo necesita leer el archivo durante su ejecución.
        #
        # Si escribiéramos DESPUÉS del yield, el proveedor intentaría leer
        # un archivo que aún no existe y fallaría con "Invalid source".
        #
        # mock.write_file() serializa las interacciones registradas en el
        # objeto pact a formato JSON según la especificación de Pact.
        # overwrite=True → sobreescribe si ya existe de una ejecución anterior.
        mock.write_file(PACT_DIR, overwrite=True)

        # yield transfiere el control a los tests del módulo.
        # mock es el objeto PactServer que expone mock.url (la URL del mock).
        yield mock

    # Al salir del "with", el servidor mock se detiene.
    # No es necesario código de limpieza adicional.


# ── Fase 1: Pruebas del Consumidor ────────────────────────────────────────────

class TestFlaskConsumer:
    """
    Define el contrato desde el punto de vista del CONSUMIDOR.

    Estos tests verifican que el mock responde exactamente como se configuró,
    y que el cliente (consumidor) puede manejar esas respuestas correctamente.

    Propósito educativo: cada test representa UNA interacción del contrato.
    El mock ya tiene las 4 interacciones registradas; cada test activa una.

    IMPORTANTE: estos tests no prueban la lógica de Flask. Prueban que el
    CONSUMIDOR sabe cómo comunicarse con la API. La app Flask no está corriendo.
    """

    def test_list_tasklists(self, pact_mock):
        # Enviamos GET al mock (no a Flask real). El mock reconoce la petición,
        # la compara con la interacción registrada y devuelve la respuesta
        # configurada (array con un objeto de ejemplo).
        r = requests.get(f"{pact_mock.url}/flask/tasklists")

        # Verificamos que el consumidor recibe lo que espera.
        assert r.status_code == 200
        assert isinstance(r.json(), list)  # el consumidor sabe que es un array

    def test_create_tasklist(self, pact_mock):
        # POST con el body exacto que el consumidor enviará en producción.
        r = requests.post(
            f"{pact_mock.url}/flask/tasklists",
            json={"name": "Shopping"},
        )
        assert r.status_code == 201
        assert r.json()["name"] == "Shopping"  # el nombre devuelto debe coincidir

    def test_get_tasklist_by_id(self, pact_mock):
        r = requests.get(f"{pact_mock.url}/flask/tasklists/1")
        assert r.status_code == 200
        # El consumidor verifica que el id devuelto es el que pidió.
        assert r.json()["id"] == 1

    def test_get_tasklist_not_found(self, pact_mock):
        r = requests.get(f"{pact_mock.url}/flask/tasklists/999")
        # El consumidor debe poder manejar un 404.
        assert r.status_code == 404


# ── Fase 2: Verificación del Proveedor ───────────────────────────────────────

@pytest.fixture(scope="class")
def flask_provider_url():
    """
    Fixture que levanta la app Flask REAL (con SQLite en memoria) en PROVIDER_PORT.

    A diferencia de las pruebas del consumidor (que usan el mock), aquí el
    verificador de Pact hará peticiones HTTP reales a la app Flask. Por eso
    necesitamos arrancarla en un hilo de background.

    scope="class" → la app se levanta una vez para toda la clase TestFlaskProvider.

    Pre-condición de datos:
      El estado "a tasklist with id 1 exists" requiere que exista una lista con
      id=1. Como SQLite usa autoincremento, la primera lista insertada tendrá id=1.
      El estado "no tasklist with id 999 exists" se satisface por defecto (ningún
      id llega a 999 en una base de datos vacía).
    """
    # Creamos una base de datos SQLite en memoria.
    # check_same_thread=False → necesario porque werkzeug usa múltiples hilos.
    # StaticPool → asegura que todos los threads usen la misma conexión en memoria
    #              (sin StaticPool, cada thread vería una base de datos diferente).
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)  # crea las tablas (tasklists, tasks)
    sf = sessionmaker(bind=engine, expire_on_commit=False)

    from app import flask_api
    from app.service import TaskListService, TaskService

    # Inyectamos los servicios con la session factory que apunta a nuestra BD
    # en memoria. Esto es dependency injection manual: reemplazamos las
    # instancias globales del módulo flask_api por instancias que usan
    # nuestra BD de prueba.
    flask_api.tasklist_service = TaskListService(session_factory=sf)
    flask_api.task_service = TaskService(session_factory=sf)

    # Insertamos la lista "Shopping" para satisfacer el estado
    # "a tasklist with id 1 exists" y "at least one tasklist exists".
    flask_api.tasklist_service.create("Shopping")

    # Creamos la app Flask y la envolvemos en un servidor werkzeug.
    app = flask_api.create_flask_app()
    server = make_server("localhost", PROVIDER_PORT, app)

    # Corremos el servidor en un hilo daemon para que no bloquee pytest.
    # daemon=True → el hilo muere automáticamente cuando el proceso principal termina.
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    # Pequeña pausa para que el servidor esté listo antes de que el
    # verificador empiece a hacer peticiones.
    time.sleep(0.3)

    yield f"http://localhost:{PROVIDER_PORT}"

    # Teardown: detenemos el servidor werkzeug limpiamente.
    server.shutdown()


class TestFlaskProvider:
    """
    Verifica que la app Flask REAL cumple el contrato generado por el consumidor.

    El verificador de Pact lee el archivo JSON del contrato y reproduce cada
    interacción contra el proveedor real. Si Flask devuelve algo diferente a
    lo especificado en el contrato (código de estado, estructura del body,
    headers), la verificación falla.

    Esto garantiza que cualquier cambio en la API Flask que rompa el contrato
    sea detectado ANTES de desplegarse a producción.
    """

    def test_provider_honours_pact(self, flask_provider_url):
        # Verifier("FlaskTasklistAPI") crea el verificador para el proveedor.
        # El nombre debe coincidir exactamente con el nombre del proveedor
        # usado en Pact("TasklistClient", "FlaskTasklistAPI").
        #
        # .add_transport(url=...) le indica a qué URL hacer las peticiones.
        # La URL debe usar el mismo host que el Verifier (por defecto "localhost").
        #
        # .add_source(PACT_FILE) le indica qué contrato verificar.
        # Acepta ruta a un archivo .json o a un directorio con múltiples contratos.
        #
        # .verify() ejecuta la verificación: reproduce cada interacción del
        # contrato contra el proveedor real y compara las respuestas.
        verifier = (
            Verifier("FlaskTasklistAPI")
            .add_transport(url=flask_provider_url)
            .add_source(PACT_FILE)
        )
        verifier.verify()

        # verifier.results es un dict con el resumen de la verificación.
        # Estructura típica:
        #   {
        #     "summary": {
        #       "testCount": 4,
        #       "failureCount": 0,
        #       "pendingCount": 0
        #     },
        #     "testResults": [...],
        #     ...
        #   }
        results = verifier.results
        failures = results.get("summary", {}).get("failureCount", 0)

        # Si failureCount > 0, al menos una interacción del contrato no fue
        # satisfecha por el proveedor. El mensaje de error incluye el dict
        # completo para facilitar el diagnóstico.
        assert failures == 0, f"El proveedor Flask no satisfizo {failures} interacción(es): {results}"
