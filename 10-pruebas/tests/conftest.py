import os

# Debe establecerse antes de importar cualquier módulo de la app, para que
# app/database.py pueda llamar a create_engine() sin fallar en entornos donde
# config.env y DATABASE_URL no existen (por ejemplo, CI/CD).
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base


@pytest.fixture(scope="function")
def test_engine():
    """Base de datos SQLite en memoria nueva por función de prueba."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        # StaticPool hace que todas las conexiones compartan la misma BD en memoria,
        # de modo que las sesiones del servicio ven los mismos datos.
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
def flask_client(session_factory, monkeypatch):
    from app import flask_api
    from app.service import TaskListService, TaskService
    monkeypatch.setattr(flask_api, "tasklist_service", TaskListService(session_factory=session_factory))
    monkeypatch.setattr(flask_api, "task_service", TaskService(session_factory=session_factory))
    app = flask_api.create_flask_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(scope="function")
def fastapi_client(session_factory, monkeypatch):
    from app import fastapi_api
    from app.service import TaskListService, TaskService
    monkeypatch.setattr(fastapi_api, "tasklist_service", TaskListService(session_factory=session_factory))
    monkeypatch.setattr(fastapi_api, "task_service", TaskService(session_factory=session_factory))
    app = fastapi_api.create_fastapi_app()
    from fastapi.testclient import TestClient
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


@pytest.fixture(scope="function")
def graphql_client(session_factory, monkeypatch):
    from app import graphql_api
    from app.service import TaskListService, TaskService
    monkeypatch.setattr(graphql_api, "tasklist_service", TaskListService(session_factory=session_factory))
    monkeypatch.setattr(graphql_api, "task_service", TaskService(session_factory=session_factory))
    app = graphql_api.create_graphql_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
