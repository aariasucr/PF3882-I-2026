from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel

from app.service import TaskListService, TaskService

tasklist_service = TaskListService()
task_service = TaskService()

router = APIRouter(prefix="/fastapi")


class TaskListCreate(BaseModel):
    name: str


class TaskCreate(BaseModel):
    description: str
    tasklist_id: int
    status: str = "pending"


class TaskUpdate(BaseModel):
    description: Optional[str] = None
    status: Optional[str] = None


@router.get("/tasklists")
def list_tasklists():
    return tasklist_service.get_all()


@router.post("/tasklists", status_code=201)
def create_tasklist(body: TaskListCreate):
    return tasklist_service.create(body.name)


@router.get("/tasklists/{id}")
def get_tasklist(id: int):
    tl = tasklist_service.get_by_id(id)
    if not tl:
        raise HTTPException(status_code=404, detail="not found")
    return tl


@router.delete("/tasklists/{id}", status_code=204)
def delete_tasklist(id: int):
    if not tasklist_service.delete(id):
        raise HTTPException(status_code=404, detail="not found")


@router.get("/tasks")
def list_tasks(tasklist_id: Optional[int] = None):
    return task_service.get_all(tasklist_id)


@router.post("/tasks", status_code=201)
def create_task(body: TaskCreate):
    try:
        return task_service.create(body.description, body.tasklist_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tasks/{id}")
def get_task(id: int):
    task = task_service.get_by_id(id)
    if not task:
        raise HTTPException(status_code=404, detail="not found")
    return task


@router.put("/tasks/{id}")
def update_task(id: int, body: TaskUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        task = task_service.update(id, **updates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not task:
        raise HTTPException(status_code=404, detail="not found")
    return task


@router.delete("/tasks/{id}", status_code=204)
def delete_task(id: int):
    if not task_service.delete(id):
        raise HTTPException(status_code=404, detail="not found")


def create_fastapi_app() -> FastAPI:
    app = FastAPI(title="TaskList FastAPI", docs_url="/fastapi/docs", openapi_url="/fastapi/openapi.json")
    app.include_router(router)
    return app
