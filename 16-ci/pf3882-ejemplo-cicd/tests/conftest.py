from app.models import Base
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
import pytest
import os

# Debe establecerse antes de importar cualquier módulo de la app, para que
# app/database.py pueda llamar a create_engine() sin fallar en entornos donde
# config.env y DATABASE_URL no existen (por ejemplo, CI/CD).
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture(scope="function")
def test_engine():
    """Base de datos SQLite en memoria nueva por función de prueba.

    Tests use metadata.create_all() instead of Alembic migrations because:
    - Each test gets a fresh in-memory database
    - No persistent state between tests
    - Fast and simple for testing

    Production uses Alembic migrations (alembic/versions/).
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def session_factory(test_engine):
    """Fábrica de sesiones SQLAlchemy ligada al motor de prueba."""
    return sessionmaker(bind=test_engine, expire_on_commit=False)


@pytest.fixture(scope="function")
def session(session_factory):
    """Sesión abierta para pruebas directas sobre el repositorio."""
    s = session_factory()
    yield s
    s.close()


# ── Clientes para pruebas de API ──────────────────────────────────────────────
#
# Cada fixture aplica monkeypatch sobre los singletons de servicio del módulo
# antes de crear la app. Los manejadores de rutas buscan esos nombres en el
# __dict__ del módulo en tiempo de ejecución, por lo que el parche es
# transparente para el código de producción.

@pytest.fixture(scope="function")
def fastapi_client(session_factory, monkeypatch):
    from app import fastapi_api
    from app.service import TaskListService, TaskService
    monkeypatch.setattr(fastapi_api, "tasklist_service",
                        TaskListService(session_factory=session_factory))
    monkeypatch.setattr(fastapi_api, "task_service",
                        TaskService(session_factory=session_factory))
    app = fastapi_api.create_fastapi_app()
    from fastapi.testclient import TestClient
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


@pytest.fixture(scope="function")
def graphql_client(session_factory, monkeypatch):
    from app import fastapi_api
    from app.service import TaskListService, TaskService
    monkeypatch.setattr(fastapi_api, "tasklist_service",
                        TaskListService(session_factory=session_factory))
    monkeypatch.setattr(fastapi_api, "task_service",
                        TaskService(session_factory=session_factory))
    app = fastapi_api.create_fastapi_app()
    from fastapi.testclient import TestClient
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client
