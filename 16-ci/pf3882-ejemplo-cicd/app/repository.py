from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models import Task, TaskList, TaskStatus


class TaskListRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_all(self) -> list[TaskList]:
        return (
            self.session.query(TaskList)
            .filter(TaskList.deleted_at.is_(None))
            .options(joinedload(TaskList.tasks))
            .all()
        )

    def get_by_id(self, id: int) -> TaskList | None:
        return (
            self.session.query(TaskList)
            .filter(TaskList.deleted_at.is_(None), TaskList.id == id)
            .options(joinedload(TaskList.tasks))
            .first()
        )

    def create(self, name: str) -> TaskList:
        tl = TaskList(name=name)
        self.session.add(tl)
        self.session.commit()
        return tl

    def delete(self, id: int) -> bool:
        tl = (
            self.session.query(TaskList)
            .filter(TaskList.deleted_at.is_(None), TaskList.id == id)
            .first()
        )
        if not tl:
            return False
        now = datetime.now(timezone.utc)
        tl.deleted_at = now
        for task in tl.tasks:
            task.deleted_at = now
        self.session.commit()
        return True

    def restore(self, id: int) -> bool:
        tl = self.session.query(TaskList).filter(TaskList.id == id).first()
        if not tl:
            return False
        tl.deleted_at = None
        for task in self.session.query(Task).filter(Task.tasklist_id == id).all():
            task.deleted_at = None
        self.session.commit()
        return True

    def purge(self, id: int) -> bool:
        tl = self.session.query(TaskList).filter(TaskList.id == id).first()
        if not tl:
            return False
        self.session.delete(tl)
        self.session.commit()
        return True


class TaskRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_all(self, tasklist_id: int | None = None) -> list[Task]:
        q = self.session.query(Task).filter(Task.deleted_at.is_(None))
        if tasklist_id is not None:
            q = q.filter(Task.tasklist_id == tasklist_id)
        return q.all()

    def get_by_id(self, id: int) -> Task | None:
        return (
            self.session.query(Task)
            .filter(Task.deleted_at.is_(None), Task.id == id)
            .first()
        )

    def create(
        self,
        description: str,
        tasklist_id: int,
        status: TaskStatus = TaskStatus.pending,
    ) -> Task:
        task = Task(description=description, tasklist_id=tasklist_id, status=status)
        self.session.add(task)
        self.session.commit()
        return task

    def update(self, id: int, **kwargs) -> Task | None:
        task = (
            self.session.query(Task)
            .filter(Task.deleted_at.is_(None), Task.id == id)
            .first()
        )
        if not task:
            return None
        for key, value in kwargs.items():
            setattr(task, key, value)
        task.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        return task

    def delete(self, id: int) -> bool:
        task = (
            self.session.query(Task)
            .filter(Task.deleted_at.is_(None), Task.id == id)
            .first()
        )
        if not task:
            return False
        task.deleted_at = datetime.now(timezone.utc)
        self.session.commit()
        return True

    def restore(self, id: int) -> bool:
        task = self.session.query(Task).filter(Task.id == id).first()
        if not task:
            return False
        task.deleted_at = None
        self.session.commit()
        return True

    def purge(self, id: int) -> bool:
        task = self.session.query(Task).filter(Task.id == id).first()
        if not task:
            return False
        self.session.delete(task)
        self.session.commit()
        return True
