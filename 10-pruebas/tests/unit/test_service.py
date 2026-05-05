"""
Pruebas del servicio (BLL) — verifican la lógica de negocio y que los servicios
retornen diccionarios planos. Cada prueba obtiene su propia base de datos SQLite
en memoria a través del fixture session_factory.
"""
import pytest
from app.service import TaskListService, TaskService


class TestTaskListService:
    @pytest.fixture(autouse=True)
    def setup(self, session_factory):
        self.svc = TaskListService(session_factory=session_factory)

    # ── create ────────────────────────────────────────────────────────────────

    def test_create_returns_dict(self):
        result = self.svc.create("Work")
        assert isinstance(result, dict)

    def test_create_sets_name(self):
        result = self.svc.create("Work")
        assert result["name"] == "Work"

    def test_create_generates_id(self):
        result = self.svc.create("Work")
        assert result["id"] is not None

    def test_create_tasks_list_is_empty(self):
        result = self.svc.create("Work")
        assert result["tasks"] == []

    # ── get_all ───────────────────────────────────────────────────────────────

    def test_get_all_empty_returns_empty_list(self):
        assert self.svc.get_all() == []

    def test_get_all_returns_list_of_dicts(self):
        self.svc.create("Work")
        result = self.svc.get_all()
        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)

    def test_get_all_returns_all_records(self):
        self.svc.create("Work")
        self.svc.create("Personal")
        assert len(self.svc.get_all()) == 2

    def test_get_all_includes_tasks(self, session_factory):
        task_svc = TaskService(session_factory=session_factory)
        tl = self.svc.create("Work")
        task_svc.create("Task A", tl["id"])
        result = self.svc.get_all()
        assert len(result[0]["tasks"]) == 1

    # ── get_by_id ─────────────────────────────────────────────────────────────

    def test_get_by_id_returns_dict(self):
        created = self.svc.create("Work")
        found = self.svc.get_by_id(created["id"])
        assert isinstance(found, dict)

    def test_get_by_id_correct_record(self):
        created = self.svc.create("Work")
        found = self.svc.get_by_id(created["id"])
        assert found["name"] == "Work"
        assert found["id"] == created["id"]

    def test_get_by_id_includes_tasks_key(self):
        created = self.svc.create("Work")
        found = self.svc.get_by_id(created["id"])
        assert "tasks" in found

    def test_get_by_id_includes_nested_tasks(self, session_factory):
        task_svc = TaskService(session_factory=session_factory)
        tl = self.svc.create("Work")
        task_svc.create("Buy milk", tl["id"])
        found = self.svc.get_by_id(tl["id"])
        assert len(found["tasks"]) == 1
        assert found["tasks"][0]["description"] == "Buy milk"

    def test_get_by_id_not_found_returns_none(self):
        assert self.svc.get_by_id(999) is None

    # ── delete ────────────────────────────────────────────────────────────────

    def test_delete_returns_true(self):
        tl = self.svc.create("Work")
        assert self.svc.delete(tl["id"]) is True

    def test_delete_removes_record(self):
        tl = self.svc.create("Work")
        self.svc.delete(tl["id"])
        assert self.svc.get_by_id(tl["id"]) is None

    def test_delete_not_found_returns_false(self):
        assert self.svc.delete(999) is False

    def test_delete_cascades_to_tasks(self, session_factory):
        task_svc = TaskService(session_factory=session_factory)
        tl = self.svc.create("Work")
        task_svc.create("Task A", tl["id"])
        self.svc.delete(tl["id"])
        assert task_svc.get_all() == []


class TestTaskService:
    @pytest.fixture(autouse=True)
    def setup(self, session_factory):
        self.svc = TaskService(session_factory=session_factory)
        tl = TaskListService(session_factory=session_factory).create("Test List")
        self.tl_id = tl["id"]

    # ── create ────────────────────────────────────────────────────────────────

    def test_create_returns_dict(self):
        result = self.svc.create("Buy milk", self.tl_id)
        assert isinstance(result, dict)

    def test_create_sets_all_fields(self):
        result = self.svc.create("Buy milk", self.tl_id)
        assert result["description"] == "Buy milk"
        assert result["tasklist_id"] == self.tl_id
        assert result["id"] is not None
        assert result["created_at"] is not None
        assert result["updated_at"] is not None

    def test_create_default_status_is_pending(self):
        result = self.svc.create("Buy milk", self.tl_id)
        assert result["status"] == "pending"

    def test_create_with_explicit_status(self):
        result = self.svc.create("Done thing", self.tl_id, status="done")
        assert result["status"] == "done"

    def test_create_all_valid_statuses(self):
        for status in ("pending", "in_progress", "done", "cancelled"):
            result = self.svc.create(f"Task {status}", self.tl_id, status=status)
            assert result["status"] == status

    def test_create_invalid_status_raises_value_error(self):
        with pytest.raises(ValueError):
            self.svc.create("Task", self.tl_id, status="invalid")

    # ── get_all ───────────────────────────────────────────────────────────────

    def test_get_all_empty_returns_empty_list(self):
        assert self.svc.get_all() == []

    def test_get_all_returns_list_of_dicts(self):
        self.svc.create("Task 1", self.tl_id)
        result = self.svc.get_all()
        assert isinstance(result, list)
        assert all(isinstance(t, dict) for t in result)

    def test_get_all_returns_all_records(self):
        self.svc.create("Task 1", self.tl_id)
        self.svc.create("Task 2", self.tl_id)
        assert len(self.svc.get_all()) == 2

    def test_get_all_filtered_by_tasklist_id(self, session_factory):
        tl2 = TaskListService(session_factory=session_factory).create("Other")
        self.svc.create("Task A", self.tl_id)
        self.svc.create("Task B", tl2["id"])
        result = self.svc.get_all(tasklist_id=self.tl_id)
        assert len(result) == 1
        assert result[0]["description"] == "Task A"

    def test_get_all_filter_unknown_tasklist_returns_empty(self):
        self.svc.create("Task", self.tl_id)
        assert self.svc.get_all(tasklist_id=999) == []

    # ── get_by_id ─────────────────────────────────────────────────────────────

    def test_get_by_id_returns_dict(self):
        task = self.svc.create("Buy milk", self.tl_id)
        found = self.svc.get_by_id(task["id"])
        assert isinstance(found, dict)

    def test_get_by_id_correct_record(self):
        task = self.svc.create("Buy milk", self.tl_id)
        found = self.svc.get_by_id(task["id"])
        assert found["description"] == "Buy milk"
        assert found["id"] == task["id"]

    def test_get_by_id_not_found_returns_none(self):
        assert self.svc.get_by_id(999) is None

    # ── update ────────────────────────────────────────────────────────────────

    def test_update_description(self):
        task = self.svc.create("Old", self.tl_id)
        updated = self.svc.update(task["id"], description="New")
        assert updated["description"] == "New"

    def test_update_status(self):
        task = self.svc.create("Task", self.tl_id)
        updated = self.svc.update(task["id"], status="in_progress")
        assert updated["status"] == "in_progress"

    def test_update_all_valid_statuses(self):
        task = self.svc.create("Task", self.tl_id)
        for status in ("pending", "in_progress", "done", "cancelled"):
            updated = self.svc.update(task["id"], status=status)
            assert updated["status"] == status

    def test_update_returns_dict(self):
        task = self.svc.create("Task", self.tl_id)
        result = self.svc.update(task["id"], description="New")
        assert isinstance(result, dict)

    def test_update_invalid_status_raises_value_error(self):
        task = self.svc.create("Task", self.tl_id)
        with pytest.raises(ValueError):
            self.svc.update(task["id"], status="invalid")

    def test_update_not_found_returns_none(self):
        assert self.svc.update(999, description="x") is None

    def test_update_persists_change(self):
        task = self.svc.create("Task", self.tl_id)
        self.svc.update(task["id"], description="Persisted")
        refetched = self.svc.get_by_id(task["id"])
        assert refetched["description"] == "Persisted"

    # ── delete ────────────────────────────────────────────────────────────────

    def test_delete_returns_true(self):
        task = self.svc.create("Task", self.tl_id)
        assert self.svc.delete(task["id"]) is True

    def test_delete_removes_record(self):
        task = self.svc.create("Task", self.tl_id)
        self.svc.delete(task["id"])
        assert self.svc.get_by_id(task["id"]) is None

    def test_delete_not_found_returns_false(self):
        assert self.svc.delete(999) is False
