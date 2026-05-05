"""
Pruebas funcionales de la API REST FastAPI.
Utiliza el TestClient de Starlette (respaldado por httpx) contra una base de datos SQLite en memoria.
Prefijo de todas las rutas: /fastapi
Nota: campos Pydantic requeridos faltantes → 422 (validación FastAPI),
      valor de status inválido → 400 (nuestro manejador de ValueError).
"""
import pytest


# ── Fixtures compartidos ──────────────────────────────────────────────────────

@pytest.fixture
def tl(fastapi_client):
    """Lista de tareas creada a través de la API FastAPI."""
    return fastapi_client.post("/fastapi/tasklists", json={"name": "Test List"}).json()


@pytest.fixture
def task(fastapi_client, tl):
    """Tarea creada a través de la API FastAPI."""
    return fastapi_client.post("/fastapi/tasks", json={
        "description": "Test Task",
        "tasklist_id": tl["id"],
    }).json()


# ── Endpoints de listas de tareas ─────────────────────────────────────────────

class TestFastAPITaskListEndpoints:
    def test_list_empty(self, fastapi_client):
        resp = fastapi_client.get("/fastapi/tasklists")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_returns_201(self, fastapi_client):
        resp = fastapi_client.post("/fastapi/tasklists", json={"name": "Work"})
        assert resp.status_code == 201

    def test_create_response_shape(self, fastapi_client):
        body = fastapi_client.post("/fastapi/tasklists", json={"name": "Work"}).json()
        assert body["name"] == "Work"
        assert isinstance(body["id"], int)
        assert body["tasks"] == []

    def test_create_missing_name_returns_422(self, fastapi_client):
        # FastAPI/Pydantic retorna 422 cuando falta un campo requerido
        resp = fastapi_client.post("/fastapi/tasklists", json={})
        assert resp.status_code == 422

    def test_list_after_create(self, fastapi_client, tl):
        body = fastapi_client.get("/fastapi/tasklists").json()
        assert len(body) == 1
        assert body[0]["id"] == tl["id"]

    def test_get_by_id(self, fastapi_client, tl):
        resp = fastapi_client.get(f"/fastapi/tasklists/{tl['id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == tl["id"]
        assert body["name"] == "Test List"
        assert "tasks" in body

    def test_get_by_id_includes_tasks(self, fastapi_client, tl, task):
        body = fastapi_client.get(f"/fastapi/tasklists/{tl['id']}").json()
        assert len(body["tasks"]) == 1
        assert body["tasks"][0]["id"] == task["id"]

    def test_get_by_id_not_found(self, fastapi_client):
        assert fastapi_client.get("/fastapi/tasklists/999").status_code == 404

    def test_delete_returns_204(self, fastapi_client, tl):
        resp = fastapi_client.delete(f"/fastapi/tasklists/{tl['id']}")
        assert resp.status_code == 204

    def test_delete_removes_from_list(self, fastapi_client, tl):
        fastapi_client.delete(f"/fastapi/tasklists/{tl['id']}")
        assert fastapi_client.get("/fastapi/tasklists").json() == []

    def test_delete_cascades_tasks(self, fastapi_client, tl, task):
        fastapi_client.delete(f"/fastapi/tasklists/{tl['id']}")
        assert fastapi_client.get("/fastapi/tasks").json() == []

    def test_delete_not_found(self, fastapi_client):
        assert fastapi_client.delete("/fastapi/tasklists/999").status_code == 404


# ── Endpoints de tareas ───────────────────────────────────────────────────────

class TestFastAPITaskEndpoints:
    def test_list_empty(self, fastapi_client):
        resp = fastapi_client.get("/fastapi/tasks")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_returns_201(self, fastapi_client, tl):
        resp = fastapi_client.post("/fastapi/tasks", json={
            "description": "Buy milk",
            "tasklist_id": tl["id"],
        })
        assert resp.status_code == 201

    def test_create_response_shape(self, fastapi_client, tl):
        body = fastapi_client.post("/fastapi/tasks", json={
            "description": "Buy milk",
            "tasklist_id": tl["id"],
        }).json()
        assert body["description"] == "Buy milk"
        assert body["status"] == "pending"
        assert body["tasklist_id"] == tl["id"]
        assert isinstance(body["id"], int)
        assert body["created_at"] is not None
        assert body["updated_at"] is not None

    def test_create_with_explicit_status(self, fastapi_client, tl):
        body = fastapi_client.post("/fastapi/tasks", json={
            "description": "Done",
            "tasklist_id": tl["id"],
            "status": "done",
        }).json()
        assert body["status"] == "done"

    def test_create_invalid_status_returns_400(self, fastapi_client, tl):
        resp = fastapi_client.post("/fastapi/tasks", json={
            "description": "Bad",
            "tasklist_id": tl["id"],
            "status": "invalid_status",
        })
        assert resp.status_code == 400

    def test_create_missing_tasklist_id_returns_422(self, fastapi_client):
        resp = fastapi_client.post("/fastapi/tasks", json={"description": "Orphan"})
        assert resp.status_code == 422

    def test_list_after_create(self, fastapi_client, task):
        body = fastapi_client.get("/fastapi/tasks").json()
        assert len(body) == 1
        assert body[0]["id"] == task["id"]

    def test_list_filtered_by_tasklist(self, fastapi_client, tl, task):
        tl2 = fastapi_client.post("/fastapi/tasklists", json={"name": "Other"}).json()
        fastapi_client.post("/fastapi/tasks", json={"description": "Other", "tasklist_id": tl2["id"]})
        result = fastapi_client.get(f"/fastapi/tasks?tasklist_id={tl['id']}").json()
        assert len(result) == 1
        assert result[0]["tasklist_id"] == tl["id"]

    def test_get_by_id(self, fastapi_client, task):
        resp = fastapi_client.get(f"/fastapi/tasks/{task['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == task["id"]

    def test_get_by_id_not_found(self, fastapi_client):
        assert fastapi_client.get("/fastapi/tasks/999").status_code == 404

    def test_update_description(self, fastapi_client, task):
        resp = fastapi_client.put(f"/fastapi/tasks/{task['id']}", json={"description": "Updated"})
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated"

    def test_update_status(self, fastapi_client, task):
        resp = fastapi_client.put(f"/fastapi/tasks/{task['id']}", json={"status": "in_progress"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

    def test_update_all_statuses(self, fastapi_client, task):
        for status in ("pending", "in_progress", "done", "cancelled"):
            body = fastapi_client.put(f"/fastapi/tasks/{task['id']}", json={"status": status}).json()
            assert body["status"] == status

    def test_update_invalid_status_returns_400(self, fastapi_client, task):
        resp = fastapi_client.put(f"/fastapi/tasks/{task['id']}", json={"status": "invalid"})
        assert resp.status_code == 400

    def test_update_not_found_returns_404(self, fastapi_client):
        resp = fastapi_client.put("/fastapi/tasks/999", json={"description": "x"})
        assert resp.status_code == 404

    def test_update_persists(self, fastapi_client, task):
        fastapi_client.put(f"/fastapi/tasks/{task['id']}", json={"description": "Persisted"})
        body = fastapi_client.get(f"/fastapi/tasks/{task['id']}").json()
        assert body["description"] == "Persisted"

    def test_delete_returns_204(self, fastapi_client, task):
        resp = fastapi_client.delete(f"/fastapi/tasks/{task['id']}")
        assert resp.status_code == 204

    def test_delete_removes_task(self, fastapi_client, task):
        fastapi_client.delete(f"/fastapi/tasks/{task['id']}")
        assert fastapi_client.get(f"/fastapi/tasks/{task['id']}").status_code == 404

    def test_delete_not_found(self, fastapi_client):
        assert fastapi_client.delete("/fastapi/tasks/999").status_code == 404
