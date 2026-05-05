from typing import List, Optional

import strawberry
from flask import Flask
from strawberry.flask.views import GraphQLView

from app.service import TaskListService, TaskService

tasklist_service = TaskListService()
task_service = TaskService()


@strawberry.type
class TaskType:
    id: int
    description: str
    status: str
    created_at: str
    updated_at: str
    tasklist_id: int


@strawberry.type
class TaskListType:
    id: int
    name: str
    tasks: List[TaskType]


def dict_to_task(d: dict) -> TaskType:
    return TaskType(
        id=d["id"],
        description=d["description"],
        status=d["status"],
        created_at=d["created_at"],
        updated_at=d["updated_at"],
        tasklist_id=d["tasklist_id"],
    )


def dict_to_tasklist(d: dict) -> TaskListType:
    return TaskListType(
        id=d["id"],
        name=d["name"],
        tasks=[dict_to_task(t) for t in d.get("tasks", [])],
    )


@strawberry.type
class Query:
    @strawberry.field
    def tasklists(self) -> List[TaskListType]:
        return [dict_to_tasklist(tl) for tl in tasklist_service.get_all()]

    @strawberry.field
    def tasklist(self, id: int) -> Optional[TaskListType]:
        d = tasklist_service.get_by_id(id)
        return dict_to_tasklist(d) if d else None

    @strawberry.field
    def tasks(self, tasklist_id: Optional[int] = None) -> List[TaskType]:
        return [dict_to_task(t) for t in task_service.get_all(tasklist_id)]

    @strawberry.field
    def task(self, id: int) -> Optional[TaskType]:
        d = task_service.get_by_id(id)
        return dict_to_task(d) if d else None


@strawberry.type
class Mutation:
    @strawberry.mutation
    def create_tasklist(self, name: str) -> TaskListType:
        d = tasklist_service.create(name)
        return dict_to_tasklist(d)

    @strawberry.mutation
    def delete_tasklist(self, id: int) -> bool:
        return tasklist_service.delete(id)

    @strawberry.mutation
    def create_task(self, description: str, tasklist_id: int, status: str = "pending") -> TaskType:
        d = task_service.create(description, tasklist_id, status)
        return dict_to_task(d)

    @strawberry.mutation
    def update_task(
        self,
        id: int,
        description: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[TaskType]:
        updates = {}
        if description is not None:
            updates["description"] = description
        if status is not None:
            updates["status"] = status
        d = task_service.update(id, **updates) if updates else task_service.get_by_id(id)
        return dict_to_task(d) if d else None

    @strawberry.mutation
    def delete_task(self, id: int) -> bool:
        return task_service.delete(id)


schema = strawberry.Schema(query=Query, mutation=Mutation)


def create_graphql_app() -> Flask:
    app = Flask(__name__)
    app.add_url_rule(
        "/graphql",
        view_func=GraphQLView.as_view("graphql_view", schema=schema),
    )
    return app
