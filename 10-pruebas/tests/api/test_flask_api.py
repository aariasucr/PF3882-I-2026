"""
Pruebas funcionales de la API REST Flask.
Utiliza el test_client integrado de Flask contra una base de datos SQLite en memoria.
Prefijo de todas las rutas: /flask
"""
import pytest


# ── Fixtures compartidos ──────────────────────────────────────────────────────

@pytest.fixture
def tl(flask_client):
    """Lista de tareas creada a través de la API Flask."""
    return flask_client.post("/flask/tasklists", json={"name": "Test List"}).get_json()


@pytest.fixture
def task(flask_client, tl):
    """Tarea creada a través de la API Flask."""
    return flask_client.post("/flask/tasks", json={
        "description": "Test Task",
        "tasklist_id": tl["id"],
    }).get_json()


# ── Endpoints de listas de tareas ─────────────────────────────────────────────

class TestFlaskTaskListEndpoints:
    def test_list_empty(self, flask_client):
        resp = flask_client.get("/flask/tasklists")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_create_returns_201(self, flask_client):
        resp = flask_client.post("/flask/tasklists", json={"name": "Work"})
        assert resp.status_code == 201

    def test_create_response_shape(self, flask_client):
        body = flask_client.post("/flask/tasklists", json={"name": "Work"}).get_json()
        assert body["name"] == "Work"
        assert isinstance(body["id"], int)
        assert body["tasks"] == []

    def test_create_missing_name_returns_400(self, flask_client):
        resp = flask_client.post("/flask/tasklists", json={})
        assert resp.status_code == 400

    def test_create_no_body_returns_4xx(self, flask_client):
        # Flask retorna 415 cuando no hay Content-Type (sin JSON), lo cual es HTTP correcto
        resp = flask_client.post("/flask/tasklists")
        assert resp.status_code >= 400

    def test_list_after_create(self, flask_client, tl):
        body = flask_client.get("/flask/tasklists").get_json()
        assert len(body) == 1
        assert body[0]["id"] == tl["id"]

    def test_get_by_id(self, flask_client, tl):
        resp = flask_client.get(f"/flask/tasklists/{tl['id']}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == tl["id"]
        assert body["name"] == "Test List"
        assert "tasks" in body

    def test_get_by_id_includes_tasks(self, flask_client, tl, task):
        body = flask_client.get(f"/flask/tasklists/{tl['id']}").get_json()
        assert len(body["tasks"]) == 1
        assert body["tasks"][0]["id"] == task["id"]

    def test_get_by_id_not_found(self, flask_client):
        assert flask_client.get("/flask/tasklists/999").status_code == 404

    def test_delete_returns_204(self, flask_client, tl):
        resp = flask_client.delete(f"/flask/tasklists/{tl['id']}")
        assert resp.status_code == 204

    def test_delete_removes_from_list(self, flask_client, tl):
        flask_client.delete(f"/flask/tasklists/{tl['id']}")
        assert flask_client.get("/flask/tasklists").get_json() == []

    def test_delete_cascades_tasks(self, flask_client, tl, task):
        flask_client.delete(f"/flask/tasklists/{tl['id']}")
        assert flask_client.get("/flask/tasks").get_json() == []

    def test_delete_not_found(self, flask_client):
        assert flask_client.delete("/flask/tasklists/999").status_code == 404


# ── Endpoints de tareas ───────────────────────────────────────────────────────

class TestFlaskTaskEndpoints:
    def test_list_empty(self, flask_client):
        resp = flask_client.get("/flask/tasks")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_create_returns_201(self, flask_client, tl):
        resp = flask_client.post("/flask/tasks", json={
            "description": "Buy milk",
            "tasklist_id": tl["id"],
        })
        assert resp.status_code == 201

    def test_create_response_shape(self, flask_client, tl):
        body = flask_client.post("/flask/tasks", json={
            "description": "Buy milk",
            "tasklist_id": tl["id"],
        }).get_json()
        assert body["description"] == "Buy milk"
        assert body["status"] == "pending"
        assert body["tasklist_id"] == tl["id"]
        assert isinstance(body["id"], int)
        assert body["created_at"] is not None
        assert body["updated_at"] is not None

    def test_create_with_explicit_status(self, flask_client, tl):
        body = flask_client.post("/flask/tasks", json={
            "description": "Done",
            "tasklist_id": tl["id"],
            "status": "done",
        }).get_json()
        assert body["status"] == "done"

    def test_create_invalid_status_returns_400(self, flask_client, tl):
        resp = flask_client.post("/flask/tasks", json={
            "description": "Bad",
            "tasklist_id": tl["id"],
            "status": "invalid_status",
        })
        assert resp.status_code == 400

    def test_create_missing_tasklist_id_returns_400(self, flask_client):
        resp = flask_client.post("/flask/tasks", json={"description": "Orphan"})
        assert resp.status_code == 400

    def test_create_missing_description_returns_400(self, flask_client, tl):
        resp = flask_client.post("/flask/tasks", json={"tasklist_id": tl["id"]})
        assert resp.status_code == 400

    def test_list_after_create(self, flask_client, task):
        body = flask_client.get("/flask/tasks").get_json()
        assert len(body) == 1
        assert body[0]["id"] == task["id"]

    def test_list_filtered_by_tasklist(self, flask_client, tl, task):
        tl2 = flask_client.post("/flask/tasklists", json={"name": "Other"}).get_json()
        flask_client.post("/flask/tasks", json={"description": "Other", "tasklist_id": tl2["id"]})
        result = flask_client.get(f"/flask/tasks?tasklist_id={tl['id']}").get_json()
        assert len(result) == 1
        assert result[0]["tasklist_id"] == tl["id"]

    def test_get_by_id(self, flask_client, task):
        resp = flask_client.get(f"/flask/tasks/{task['id']}")
        assert resp.status_code == 200
        assert resp.get_json()["id"] == task["id"]

    def test_get_by_id_not_found(self, flask_client):
        assert flask_client.get("/flask/tasks/999").status_code == 404

    def test_update_description(self, flask_client, task):
        resp = flask_client.put(f"/flask/tasks/{task['id']}", json={"description": "Updated"})
        assert resp.status_code == 200
        assert resp.get_json()["description"] == "Updated"

    def test_update_status(self, flask_client, task):
        resp = flask_client.put(f"/flask/tasks/{task['id']}", json={"status": "in_progress"})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "in_progress"

    def test_update_all_statuses(self, flask_client, task):
        for status in ("pending", "in_progress", "done", "cancelled"):
            body = flask_client.put(f"/flask/tasks/{task['id']}", json={"status": status}).get_json()
            assert body["status"] == status

    def test_update_invalid_status_returns_400(self, flask_client, task):
        resp = flask_client.put(f"/flask/tasks/{task['id']}", json={"status": "invalid"})
        assert resp.status_code == 400

    def test_update_not_found_returns_404(self, flask_client):
        resp = flask_client.put("/flask/tasks/999", json={"description": "x"})
        assert resp.status_code == 404

    def test_update_persists(self, flask_client, task):
        flask_client.put(f"/flask/tasks/{task['id']}", json={"description": "Persisted"})
        body = flask_client.get(f"/flask/tasks/{task['id']}").get_json()
        assert body["description"] == "Persisted"

    def test_delete_returns_204(self, flask_client, task):
        resp = flask_client.delete(f"/flask/tasks/{task['id']}")
        assert resp.status_code == 204

    def test_delete_removes_task(self, flask_client, task):
        flask_client.delete(f"/flask/tasks/{task['id']}")
        assert flask_client.get(f"/flask/tasks/{task['id']}").status_code == 404

    def test_delete_not_found(self, flask_client):
        assert flask_client.delete("/flask/tasks/999").status_code == 404
