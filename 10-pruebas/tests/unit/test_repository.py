"""
Pruebas del repositorio (DAL) — verifican operaciones CRUD básicas contra una
base de datos SQLite en memoria.
"""
import pytest
from app.models import TaskStatus
from app.repository import TaskListRepository, TaskRepository


class TestTaskListRepository:
    def test_create_returns_object_with_id(self, session):
        tl = TaskListRepository(session).create("Work")
        assert tl.id is not None
        assert tl.name == "Work"

    def test_get_all_returns_all_records(self, session):
        repo = TaskListRepository(session)
        repo.create("Work")
        repo.create("Personal")
        assert len(repo.get_all()) == 2

    def test_get_all_empty_database(self, session):
        assert TaskListRepository(session).get_all() == []

    def test_get_by_id_returns_correct_record(self, session):
        repo = TaskListRepository(session)
        created = repo.create("Work")
        found = repo.get_by_id(created.id)
        assert found is not None
        assert found.name == "Work"

    def test_get_by_id_includes_tasks_via_joinedload(self, session):
        repo = TaskListRepository(session)
        task_repo = TaskRepository(session)
        tl = repo.create("Work")
        task_repo.create("Task A", tl.id)
        found = repo.get_by_id(tl.id)
        assert len(found.tasks) == 1
        assert found.tasks[0].description == "Task A"

    def test_get_by_id_not_found_returns_none(self, session):
        assert TaskListRepository(session).get_by_id(999) is None

    def test_delete_returns_true(self, session):
        repo = TaskListRepository(session)
        tl = repo.create("Work")
        assert repo.delete(tl.id) is True

    def test_delete_removes_record(self, session):
        repo = TaskListRepository(session)
        tl = repo.create("Work")
        repo.delete(tl.id)
        assert repo.get_by_id(tl.id) is None

    def test_delete_not_found_returns_false(self, session):
        assert TaskListRepository(session).delete(999) is False

    def test_delete_cascades_to_tasks(self, session):
        tl_repo = TaskListRepository(session)
        task_repo = TaskRepository(session)
        tl = tl_repo.create("Work")
        task_repo.create("Task A", tl.id)
        task_repo.create("Task B", tl.id)
        tl_repo.delete(tl.id)
        assert task_repo.get_all() == []


class TestTaskRepository:
    @pytest.fixture(autouse=True)
    def tasklist(self, session):
        tl = TaskListRepository(session).create("Test List")
        self.tl_id = tl.id

    def test_create_with_default_status(self, session):
        task = TaskRepository(session).create("Buy milk", self.tl_id)
        assert task.id is not None
        assert task.description == "Buy milk"
        assert task.status == TaskStatus.pending
        assert task.tasklist_id == self.tl_id
        assert task.created_at is not None
        assert task.updated_at is not None

    def test_create_with_explicit_status(self, session):
        task = TaskRepository(session).create(
            "Done thing", self.tl_id, TaskStatus.done)
        assert task.status == TaskStatus.done

    def test_create_all_statuses(self, session):
        repo = TaskRepository(session)
        for status in TaskStatus:
            task = repo.create(f"Task {status.value}", self.tl_id, status)
            assert task.status == status

    def test_get_all_returns_all_records(self, session):
        repo = TaskRepository(session)
        repo.create("Task 1", self.tl_id)
        repo.create("Task 2", self.tl_id)
        assert len(repo.get_all()) == 2

    def test_get_all_empty_database(self, session):
        assert TaskRepository(session).get_all() == []

    def test_get_all_filtered_by_tasklist_id(self, session):
        tl2 = TaskListRepository(session).create("Other List")
        repo = TaskRepository(session)
        repo.create("Task A", self.tl_id)
        repo.create("Task B", tl2.id)
        result = repo.get_all(tasklist_id=self.tl_id)
        assert len(result) == 1
        assert result[0].description == "Task A"

    def test_get_all_filter_returns_empty_for_unknown_tasklist(self, session):
        TaskRepository(session).create("Task", self.tl_id)
        assert TaskRepository(session).get_all(tasklist_id=999) == []

    def test_get_by_id_returns_correct_record(self, session):
        repo = TaskRepository(session)
        created = repo.create("Buy milk", self.tl_id)
        found = repo.get_by_id(created.id)
        assert found is not None
        assert found.description == "Buy milk"

    def test_get_by_id_not_found_returns_none(self, session):
        assert TaskRepository(session).get_by_id(999) is None

    def test_update_description(self, session):
        repo = TaskRepository(session)
        task = repo.create("Old description", self.tl_id)
        updated = repo.update(task.id, description="New description")
        assert updated.description == "New description"

    def test_update_status(self, session):
        repo = TaskRepository(session)
        task = repo.create("Task", self.tl_id)
        updated = repo.update(task.id, status=TaskStatus.done)
        assert updated.status == TaskStatus.done

    def test_update_bumps_updated_at(self, session):
        import time
        repo = TaskRepository(session)
        task = repo.create("Task", self.tl_id)
        original_ts = task.updated_at
        time.sleep(0.01)
        updated = repo.update(task.id, description="Changed")
        assert updated.updated_at > original_ts

    def test_update_does_not_change_created_at(self, session):
        repo = TaskRepository(session)
        task = repo.create("Task", self.tl_id)
        original_created = task.created_at
        repo.update(task.id, description="Changed")
        refetched = repo.get_by_id(task.id)
        assert refetched.created_at == original_created

    def test_update_not_found_returns_none(self, session):
        assert TaskRepository(session).update(999, description="x") is None

    def test_delete_returns_true(self, session):
        repo = TaskRepository(session)
        task = repo.create("Task", self.tl_id)
        assert repo.delete(task.id) is True

    def test_delete_removes_record(self, session):
        repo = TaskRepository(session)
        task = repo.create("Task", self.tl_id)
        repo.delete(task.id)
        assert repo.get_by_id(task.id) is None

    def test_delete_not_found_returns_false(self, session):
        assert TaskRepository(session).delete(999) is False
