"""
Pruebas funcionales de la API GraphQL.
Utiliza Flask test_client para hacer POST a /graphql (Strawberry sobre Flask).
Todas las peticiones son JSON: {"query": "...", "variables": {...}}
Respuestas: {"data": {...}} en éxito, {"errors": [...]} en fallo.
"""
import pytest


def gql(client, query: str, variables: dict = None) -> tuple[dict | None, list | None]:
    """Envía una petición GraphQL y retorna (data, errors)."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = client.post("/graphql", json=payload)
    body = resp.get_json()
    return body.get("data"), body.get("errors")


# ── Fixtures compartidos ──────────────────────────────────────────────────────

@pytest.fixture
def tl(graphql_client):
    """Lista de tareas creada a través de la API GraphQL."""
    data, _ = gql(
        graphql_client,
        "mutation CreateTL($name: String!) { createTasklist(name: $name) { id name tasks { id } } }",
        {"name": "Test List"},
    )
    return data["createTasklist"]


@pytest.fixture
def task(graphql_client, tl):
    """Tarea creada a través de la API GraphQL."""
    data, _ = gql(
        graphql_client,
        "mutation CreateT($desc: String!, $tlId: Int!) { createTask(description: $desc, tasklistId: $tlId) { id description status tasklistId createdAt updatedAt } }",
        {"desc": "Test Task", "tlId": tl["id"]},
    )
    return data["createTask"]


# ── Pruebas de queries ────────────────────────────────────────────────────────

class TestGraphQLQueries:
    def test_tasklists_empty(self, graphql_client):
        data, errors = gql(graphql_client, "{ tasklists { id name } }")
        assert errors is None
        assert data["tasklists"] == []

    def test_tasklists_returns_created(self, graphql_client, tl):
        data, errors = gql(graphql_client, "{ tasklists { id name } }")
        assert errors is None
        assert len(data["tasklists"]) == 1
        assert data["tasklists"][0]["name"] == "Test List"

    def test_tasklists_includes_tasks(self, graphql_client, tl, task):
        data, errors = gql(graphql_client, "{ tasklists { id tasks { id description } } }")
        assert errors is None
        tasks = data["tasklists"][0]["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["description"] == "Test Task"

    def test_tasklist_by_id(self, graphql_client, tl):
        data, errors = gql(
            graphql_client,
            "query Get($id: Int!) { tasklist(id: $id) { id name } }",
            {"id": tl["id"]},
        )
        assert errors is None
        assert data["tasklist"]["id"] == tl["id"]
        assert data["tasklist"]["name"] == "Test List"

    def test_tasklist_by_id_includes_tasks(self, graphql_client, tl, task):
        data, errors = gql(
            graphql_client,
            "query Get($id: Int!) { tasklist(id: $id) { tasks { id description status } } }",
            {"id": tl["id"]},
        )
        assert errors is None
        tasks = data["tasklist"]["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["description"] == "Test Task"
        assert tasks[0]["status"] == "pending"

    def test_tasklist_by_id_not_found(self, graphql_client):
        data, errors = gql(graphql_client, "{ tasklist(id: 999) { id } }")
        assert errors is None
        assert data["tasklist"] is None

    def test_tasks_empty(self, graphql_client):
        data, errors = gql(graphql_client, "{ tasks { id } }")
        assert errors is None
        assert data["tasks"] == []

    def test_tasks_returns_created(self, graphql_client, task):
        data, errors = gql(graphql_client, "{ tasks { id description status tasklistId } }")
        assert errors is None
        assert len(data["tasks"]) == 1
        t = data["tasks"][0]
        assert t["description"] == "Test Task"
        assert t["status"] == "pending"

    def test_tasks_filtered_by_tasklist(self, graphql_client, tl, task):
        # segunda lista + tarea — no deben aparecer en el resultado filtrado
        data2, _ = gql(graphql_client, 'mutation { createTasklist(name: "Other") { id } }')
        tl2_id = data2["createTasklist"]["id"]
        gql(
            graphql_client,
            "mutation C($desc: String!, $id: Int!) { createTask(description: $desc, tasklistId: $id) { id } }",
            {"desc": "Other Task", "id": tl2_id},
        )
        data, errors = gql(
            graphql_client,
            "query F($tlId: Int!) { tasks(tasklistId: $tlId) { id tasklistId } }",
            {"tlId": tl["id"]},
        )
        assert errors is None
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["tasklistId"] == tl["id"]

    def test_task_by_id(self, graphql_client, task):
        data, errors = gql(
            graphql_client,
            "query Get($id: Int!) { task(id: $id) { id description status } }",
            {"id": task["id"]},
        )
        assert errors is None
        assert data["task"]["id"] == task["id"]
        assert data["task"]["description"] == "Test Task"

    def test_task_by_id_not_found(self, graphql_client):
        data, errors = gql(graphql_client, "{ task(id: 999) { id } }")
        assert errors is None
        assert data["task"] is None

    def test_task_has_timestamps(self, graphql_client, task):
        data, errors = gql(
            graphql_client,
            "query Get($id: Int!) { task(id: $id) { createdAt updatedAt } }",
            {"id": task["id"]},
        )
        assert errors is None
        assert data["task"]["createdAt"] is not None
        assert data["task"]["updatedAt"] is not None


# ── Pruebas de mutations ──────────────────────────────────────────────────────

class TestGraphQLMutations:
    def test_create_tasklist(self, graphql_client):
        data, errors = gql(
            graphql_client,
            "mutation C($name: String!) { createTasklist(name: $name) { id name tasks { id } } }",
            {"name": "Work"},
        )
        assert errors is None
        body = data["createTasklist"]
        assert body["name"] == "Work"
        assert isinstance(body["id"], int)
        assert body["tasks"] == []

    def test_create_tasklist_appears_in_list(self, graphql_client):
        gql(graphql_client, 'mutation { createTasklist(name: "Work") { id } }')
        data, _ = gql(graphql_client, "{ tasklists { name } }")
        assert any(tl["name"] == "Work" for tl in data["tasklists"])

    def test_delete_tasklist_returns_true(self, graphql_client, tl):
        data, errors = gql(
            graphql_client,
            "mutation D($id: Int!) { deleteTasklist(id: $id) }",
            {"id": tl["id"]},
        )
        assert errors is None
        assert data["deleteTasklist"] is True

    def test_delete_tasklist_removes_record(self, graphql_client, tl):
        gql(graphql_client, "mutation D($id: Int!) { deleteTasklist(id: $id) }", {"id": tl["id"]})
        data, _ = gql(graphql_client, "{ tasklists { id } }")
        assert data["tasklists"] == []

    def test_delete_tasklist_not_found(self, graphql_client):
        data, errors = gql(graphql_client, "mutation { deleteTasklist(id: 999) }")
        assert errors is None
        assert data["deleteTasklist"] is False

    def test_create_task(self, graphql_client, tl):
        data, errors = gql(
            graphql_client,
            "mutation C($desc: String!, $tlId: Int!) { createTask(description: $desc, tasklistId: $tlId) { id description status tasklistId } }",
            {"desc": "Buy milk", "tlId": tl["id"]},
        )
        assert errors is None
        t = data["createTask"]
        assert t["description"] == "Buy milk"
        assert t["status"] == "pending"
        assert t["tasklistId"] == tl["id"]
        assert isinstance(t["id"], int)

    def test_create_task_with_status(self, graphql_client, tl):
        data, errors = gql(
            graphql_client,
            "mutation C($desc: String!, $tlId: Int!, $st: String!) { createTask(description: $desc, tasklistId: $tlId, status: $st) { status } }",
            {"desc": "Done", "tlId": tl["id"], "st": "done"},
        )
        assert errors is None
        assert data["createTask"]["status"] == "done"

    def test_update_task_description(self, graphql_client, task):
        data, errors = gql(
            graphql_client,
            "mutation U($id: Int!, $desc: String!) { updateTask(id: $id, description: $desc) { id description } }",
            {"id": task["id"], "desc": "Updated description"},
        )
        assert errors is None
        assert data["updateTask"]["description"] == "Updated description"

    def test_update_task_status(self, graphql_client, task):
        data, errors = gql(
            graphql_client,
            "mutation U($id: Int!, $st: String!) { updateTask(id: $id, status: $st) { id status } }",
            {"id": task["id"], "st": "done"},
        )
        assert errors is None
        assert data["updateTask"]["status"] == "done"

    def test_update_task_all_statuses(self, graphql_client, task):
        for status in ("pending", "in_progress", "done", "cancelled"):
            data, errors = gql(
                graphql_client,
                "mutation U($id: Int!, $st: String!) { updateTask(id: $id, status: $st) { status } }",
                {"id": task["id"], "st": status},
            )
            assert errors is None
            assert data["updateTask"]["status"] == status

    def test_update_task_not_found(self, graphql_client):
        data, errors = gql(
            graphql_client,
            "mutation { updateTask(id: 999, description: \"x\") { id } }",
        )
        assert errors is None
        assert data["updateTask"] is None

    def test_update_task_persists(self, graphql_client, task):
        gql(
            graphql_client,
            "mutation U($id: Int!, $desc: String!) { updateTask(id: $id, description: $desc) { id } }",
            {"id": task["id"], "desc": "Persisted"},
        )
        data, _ = gql(
            graphql_client,
            "query G($id: Int!) { task(id: $id) { description } }",
            {"id": task["id"]},
        )
        assert data["task"]["description"] == "Persisted"

    def test_delete_task_returns_true(self, graphql_client, task):
        data, errors = gql(
            graphql_client,
            "mutation D($id: Int!) { deleteTask(id: $id) }",
            {"id": task["id"]},
        )
        assert errors is None
        assert data["deleteTask"] is True

    def test_delete_task_removes_record(self, graphql_client, task):
        gql(graphql_client, "mutation D($id: Int!) { deleteTask(id: $id) }", {"id": task["id"]})
        data, _ = gql(graphql_client, "query G($id: Int!) { task(id: $id) { id } }", {"id": task["id"]})
        assert data["task"] is None

    def test_delete_task_not_found(self, graphql_client):
        data, errors = gql(graphql_client, "mutation { deleteTask(id: 999) }")
        assert errors is None
        assert data["deleteTask"] is False
