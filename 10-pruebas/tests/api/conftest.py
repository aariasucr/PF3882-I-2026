import pytest
import schemathesis.openapi as oa
import schemathesis.graphql as gql


@pytest.fixture
def flask_schema(session_factory, monkeypatch):
    from app import flask_api
    from app.service import TaskListService, TaskService
    monkeypatch.setattr(flask_api, "tasklist_service", TaskListService(session_factory=session_factory))
    monkeypatch.setattr(flask_api, "task_service", TaskService(session_factory=session_factory))
    app = flask_api.create_flask_app()
    return oa.from_wsgi("/flask/apispec.json", app=app)


@pytest.fixture
def fastapi_schema(session_factory, monkeypatch):
    from app import fastapi_api
    from app.service import TaskListService, TaskService
    monkeypatch.setattr(fastapi_api, "tasklist_service", TaskListService(session_factory=session_factory))
    monkeypatch.setattr(fastapi_api, "task_service", TaskService(session_factory=session_factory))
    app = fastapi_api.create_fastapi_app()
    return oa.from_asgi("/fastapi/openapi.json", app=app)


@pytest.fixture
def graphql_schema(session_factory, monkeypatch):
    from app import graphql_api
    from app.service import TaskListService, TaskService
    monkeypatch.setattr(graphql_api, "tasklist_service", TaskListService(session_factory=session_factory))
    monkeypatch.setattr(graphql_api, "task_service", TaskService(session_factory=session_factory))
    app = graphql_api.create_graphql_app()
    return gql.from_wsgi("/graphql", app=app)
