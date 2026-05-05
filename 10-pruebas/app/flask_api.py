from flask import Flask, Blueprint, request, jsonify
from flasgger import Swagger
from app.service import TaskListService, TaskService

tasklist_service = TaskListService()
task_service = TaskService()

bp = Blueprint("flask_rest", __name__, url_prefix="/flask")

SWAGGER_CONFIG = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/flask/apispec.json",
            "rule_filter": lambda rule: rule.rule.startswith("/flask"),
            "model_filter": lambda _tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/flask/docs",
}

SWAGGER_TEMPLATE = {
    "info": {
        "title": "TaskList Flask REST API",
        "description": "API REST para gestión de listas de tareas (Flask)",
        "version": "1.0.0",
    },
    "basePath": "/",
    "schemes": ["http"],
}


# ── Listas de tareas ──────────────────────────────────────────────────────────

@bp.get("/tasklists")
def list_tasklists():
    """
    Lista todas las listas de tareas
    ---
    tags:
      - tasklists
    responses:
      200:
        description: Lista de listas de tareas con sus tareas
        schema:
          type: array
          items:
            $ref: '#/definitions/TaskList'
    definitions:
      Task:
        type: object
        properties:
          id:          {type: integer}
          description: {type: string}
          status:      {type: string, enum: [pending, in_progress, done, cancelled]}
          created_at:  {type: string, format: date-time}
          updated_at:  {type: string, format: date-time}
          tasklist_id: {type: integer}
      TaskList:
        type: object
        properties:
          id:    {type: integer}
          name:  {type: string}
          tasks:
            type: array
            items:
              $ref: '#/definitions/Task'
    """
    return jsonify(tasklist_service.get_all())


@bp.post("/tasklists")
def create_tasklist():
    """
    Crea una lista de tareas
    ---
    tags:
      - tasklists
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [name]
          properties:
            name: {type: string, example: "Shopping"}
    responses:
      201:
        description: Lista de tareas creada
        schema:
          $ref: '#/definitions/TaskList'
      400:
        description: Campo requerido faltante
    """
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "name is required"}), 400
    return jsonify(tasklist_service.create(data["name"])), 201


@bp.get("/tasklists/<int:id>")
def get_tasklist(id):
    """
    Obtiene una lista de tareas por ID
    ---
    tags:
      - tasklists
    parameters:
      - in: path
        name: id
        type: integer
        required: true
    responses:
      200:
        description: Lista de tareas con sus tareas
        schema:
          $ref: '#/definitions/TaskList'
      404:
        description: No encontrada
    """
    tl = tasklist_service.get_by_id(id)
    if not tl:
        return jsonify({"error": "not found"}), 404
    return jsonify(tl)


@bp.delete("/tasklists/<int:id>")
def delete_tasklist(id):
    """
    Elimina una lista de tareas (en cascada a sus tareas)
    ---
    tags:
      - tasklists
    parameters:
      - in: path
        name: id
        type: integer
        required: true
    responses:
      204:
        description: Eliminada
      404:
        description: No encontrada
    """
    if not tasklist_service.delete(id):
        return jsonify({"error": "not found"}), 404
    return "", 204


# ── Tareas ────────────────────────────────────────────────────────────────────

@bp.get("/tasks")
def list_tasks():
    """
    Lista las tareas
    ---
    tags:
      - tasks
    parameters:
      - in: query
        name: tasklist_id
        type: integer
        required: false
        description: Filtrar por lista de tareas
    responses:
      200:
        description: Lista de tareas
        schema:
          type: array
          items:
            $ref: '#/definitions/Task'
    """
    tasklist_id = request.args.get("tasklist_id", type=int)
    return jsonify(task_service.get_all(tasklist_id))


@bp.post("/tasks")
def create_task():
    """
    Crea una tarea
    ---
    tags:
      - tasks
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [description, tasklist_id]
          properties:
            description:  {type: string, example: "Buy milk"}
            tasklist_id:  {type: integer, example: 1}
            status:
              type: string
              enum: [pending, in_progress, done, cancelled]
              default: pending
    responses:
      201:
        description: Tarea creada
        schema:
          $ref: '#/definitions/Task'
      400:
        description: Error de validación
    """
    data = request.get_json()
    if not data or "description" not in data or "tasklist_id" not in data:
        return jsonify({"error": "description and tasklist_id are required"}), 400
    try:
        task = task_service.create(
            description=data["description"],
            tasklist_id=data["tasklist_id"],
            status=data.get("status", "pending"),
        )
        return jsonify(task), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/tasks/<int:id>")
def get_task(id):
    """
    Obtiene una tarea por ID
    ---
    tags:
      - tasks
    parameters:
      - in: path
        name: id
        type: integer
        required: true
    responses:
      200:
        description: Tarea
        schema:
          $ref: '#/definitions/Task'
      404:
        description: No encontrada
    """
    task = task_service.get_by_id(id)
    if not task:
        return jsonify({"error": "not found"}), 404
    return jsonify(task)


@bp.put("/tasks/<int:id>")
def update_task(id):
    """
    Actualiza una tarea
    ---
    tags:
      - tasks
    parameters:
      - in: path
        name: id
        type: integer
        required: true
      - in: body
        name: body
        schema:
          type: object
          properties:
            description: {type: string}
            status:
              type: string
              enum: [pending, in_progress, done, cancelled]
    responses:
      200:
        description: Tarea actualizada
        schema:
          $ref: '#/definitions/Task'
      400:
        description: Valor de status inválido
      404:
        description: No encontrada
    """
    data = request.get_json() or {}
    updates = {k: v for k, v in data.items() if k in ("description", "status")}
    try:
        task = task_service.update(id, **updates)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not task:
        return jsonify({"error": "not found"}), 404
    return jsonify(task)


@bp.delete("/tasks/<int:id>")
def delete_task(id):
    """
    Elimina una tarea
    ---
    tags:
      - tasks
    parameters:
      - in: path
        name: id
        type: integer
        required: true
    responses:
      204:
        description: Eliminada
      404:
        description: No encontrada
    """
    if not task_service.delete(id):
        return jsonify({"error": "not found"}), 404
    return "", 204


def create_flask_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(bp)
    Swagger(app, config=SWAGGER_CONFIG, template=SWAGGER_TEMPLATE)
    return app
