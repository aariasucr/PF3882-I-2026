from typing import List, Optional

import strawberry
from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel
from strawberry.fastapi import GraphQLRouter

from app.service import TaskListService, TaskService

tasklist_service = TaskListService()
task_service = TaskService()

rest_router = APIRouter(prefix="/api/v1")
rest_router2 = APIRouter(prefix="/api/v2")


class TaskListCreate(BaseModel):
    name: str


class TaskCreate(BaseModel):
    description: str
    tasklist_id: int
    status: str = "pending"


class TaskUpdate(BaseModel):
    description: Optional[str] = None
    status: Optional[str] = None


@rest_router.get("/tasklists")
def list_tasklists():
    return tasklist_service.get_all()


@rest_router2.get("/tasklists", tags=["v2"])
def list_tasklistsv2():
    return tasklist_service.get_all()


@rest_router.post(
    "/tasklists",
    status_code=201,
)
def create_tasklist(body: TaskListCreate):
    return tasklist_service.create(body.name)


@rest_router.get("/tasklists/{id}")
def get_tasklist(id: int):
    tl = tasklist_service.get_by_id(id)
    if not tl:
        raise HTTPException(status_code=404, detail="not found")
    return tl


@rest_router.delete("/tasklists/{id}", status_code=204)
def delete_tasklist(id: int):
    if not tasklist_service.delete(id):
        raise HTTPException(status_code=404, detail="not found")


@rest_router.get("/tasks")
def list_tasks(tasklist_id: Optional[int] = None):
    return task_service.get_all(tasklist_id)


@rest_router.post("/tasks", status_code=201)
def create_task(body: TaskCreate):
    try:
        return task_service.create(body.description, body.tasklist_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@rest_router.get("/tasks/{id}")
def get_task(id: int):
    task = task_service.get_by_id(id)
    if not task:
        raise HTTPException(status_code=404, detail="not found")
    return task


@rest_router.put("/tasks/{id}")
def update_task(id: int, body: TaskUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        task = task_service.update(id, **updates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not task:
        raise HTTPException(status_code=404, detail="not found")
    return task


@rest_router.delete("/tasks/{id}", status_code=204)
def delete_task(id: int):
    if not task_service.delete(id):
        raise HTTPException(status_code=404, detail="not found")


@strawberry.type
class TaskType:
    id: int
    description: str
    status: str
    created_at: str
    updated_at: str
    tasklist_id: int = strawberry.field(deprecation_reason="Use tasklist instead")
    tasklist: int


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
        tasklist=d["tasklist_id"],
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
    def create_task(
        self, description: str, tasklist_id: int, status: str = "pending"
    ) -> TaskType:
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
        d = (
            task_service.update(id, **updates)
            if updates
            else task_service.get_by_id(id)
        )
        return dict_to_task(d) if d else None

    @strawberry.mutation
    def delete_task(self, id: int) -> bool:
        return task_service.delete(id)


schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_router = GraphQLRouter(schema, path="/graphql")


def create_fastapi_app() -> FastAPI:
    app = FastAPI(title="TaskList API", docs_url="/docs", openapi_url="/openapi.json")
    app.include_router(rest_router)
    app.include_router(rest_router2)
    app.include_router(graphql_router)
    return app
