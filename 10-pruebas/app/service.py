from app.database import SessionLocal
from app.models import TaskStatus
from app.repository import TaskListRepository, TaskRepository


class TaskListService:
    def __init__(self, session_factory=None):
        self._sf = session_factory or SessionLocal

    def get_all(self) -> list[dict]:
        with self._sf() as session:
            items = TaskListRepository(session).get_all()
            return [tl.to_dict() for tl in items]

    def get_by_id(self, id: int) -> dict | None:
        with self._sf() as session:
            tl = TaskListRepository(session).get_by_id(id)
            return tl.to_dict() if tl else None

    def create(self, name: str) -> dict:
        with self._sf() as session:
            tl = TaskListRepository(session).create(name)
            return {"id": tl.id, "name": tl.name, "tasks": []}

    def delete(self, id: int) -> bool:
        with self._sf() as session:
            return TaskListRepository(session).delete(id)


class TaskService:
    def __init__(self, session_factory=None):
        self._sf = session_factory or SessionLocal

    def get_all(self, tasklist_id: int | None = None) -> list[dict]:
        with self._sf() as session:
            tasks = TaskRepository(session).get_all(tasklist_id)
            return [t.to_dict() for t in tasks]

    def get_by_id(self, id: int) -> dict | None:
        with self._sf() as session:
            task = TaskRepository(session).get_by_id(id)
            return task.to_dict() if task else None

    def create(self, description: str, tasklist_id: int, status: str = "pending") -> dict:
        status_enum = TaskStatus(status)
        with self._sf() as session:
            task = TaskRepository(session).create(description, tasklist_id, status_enum)
            return task.to_dict()

    def update(self, id: int, **kwargs) -> dict | None:
        if "status" in kwargs and kwargs["status"] is not None:
            kwargs["status"] = TaskStatus(kwargs["status"])
        with self._sf() as session:
            task = TaskRepository(session).update(id, **kwargs)
            return task.to_dict() if task else None

    def delete(self, id: int) -> bool:
        with self._sf() as session:
            return TaskRepository(session).delete(id)
