from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

app = FastAPI(
    title="API REST Básica",
    description="API de ejemplo para gestionar ítems (crear, listar, obtener, actualizar y eliminar). Documentación disponible en Redoc y Swagger UI.",
    version="1.0.0",
)


class Item(BaseModel):
    id: int = Field(..., description="Identificador único del ítem")
    name: str = Field(..., description="Nombre del ítem")
    description: str | None = Field(
        None, description="Descripción opcional del ítem")


class ItemCreate(BaseModel):
    name: str = Field(..., description="Nombre del ítem")
    description: str | None = Field(
        None, description="Descripción opcional del ítem")


class ItemUpdate(BaseModel):
    name: str | None = Field(
        None, description="Nuevo nombre del ítem (opcional)")
    description: str | None = Field(
        None, description="Nueva descripción del ítem (opcional)")


class ErrorResponse(BaseModel):
    code: int = Field(..., description="Código de estado HTTP")
    message: str = Field(..., description="Mensaje de error")


ITEMS: list[Item] = [
    Item(id=1, name="Monitor", description="Un monitor de 24 pulgadas"),
    Item(id=2, name="Keyboard", description="Un teclado mecânico"),
    Item(id=3, name="Mouse", description="Un mouse óptico"),
]


@app.get(
    "/",
    summary="Raíz",
    description="Mensaje de bienvenida a la API REST Básica.",
    tags=["General"],
)
def root() -> dict[str, str]:
    return {"message": "Welcome to the Basic REST API"}


@app.get(
    "/items",
    response_model=list[Item],
    summary="Listar ítems",
    description="Devuelve la lista completa de ítems almacenados.",
    tags=["Items"]
)
def list_items() -> list[Item]:
    return ITEMS


@app.get(
    "/items/{item_id}",
    response_model=Item,
    summary="Obtener un ítem",
    description="Obtiene un ítem por su identificador. Devuelve 404 si no existe.",
    tags=["Items"]
)
def get_item(item_id: int = Path(..., description="Identificador del ítem")) -> Item:
    for item in ITEMS:
        if item.id == item_id:
            return item
    raise HTTPException(status_code=404, detail="Item not found")


@app.post(
    "/items",
    response_model=Item,
    status_code=201,
    summary="Crear ítem",
    description="Crea un nuevo ítem. El identificador se genera automáticamente.",
    tags=["Items"]
)
def create_item(body: ItemCreate) -> Item:
    next_id = max((i.id for i in ITEMS), default=0) + 1
    item = Item(id=next_id, name=body.name, description=body.description)
    ITEMS.append(item)
    return item


@app.put(
    "/items/{item_id}",
    response_model=Item,
    summary="Actualizar ítem",
    description="Actualiza un ítem existente por identificador. Solo se modifican los campos enviados.",
    tags=["Items"]
)
def update_item(
    item_id: int = Path(...,
                        description="Identificador del ítem a actualizar"),
    body: ItemUpdate = ...,
) -> Item:
    for i, item in enumerate(ITEMS):
        if item.id == item_id:
            data = item.model_dump()
            if body.name is not None:
                data["name"] = body.name
            if body.description is not None:
                data["description"] = body.description
            ITEMS[i] = Item(**data)
            return ITEMS[i]
    raise HTTPException(status_code=404, detail="Item not found")


@app.delete(
    "/items/{item_id}",
    status_code=204,
    summary="Eliminar ítem",
    description="Elimina un ítem por identificador. Respuesta sin contenido (204).",
    tags=["Items"]
)
def delete_item(item_id: int = Path(..., description="Identificador del ítem a eliminar")) -> None:
    for i, item in enumerate(ITEMS):
        if item.id == item_id:
            ITEMS.pop(i)
            return
    raise HTTPException(status_code=404, detail="Item not found")


@app.delete(
    "/items/otrodelete/{item_id}",
    response_model=None,
    summary="Eliminar ítem (alternativo)",
    description="Elimina un ítem por identificador. Versión alternativa que devuelve ErrorResponse en 404.",
    responses={
        204: {"description": "Ítem borrado correctamente"},
        404: {"description": "Ítem no encontrado", "model": ErrorResponse},
    },
    tags=["Items"]
)
def otro_delete_item(
    item_id: int = Path(..., description="Identificador del ítem a eliminar"),
) -> Response | JSONResponse:
    for i, item in enumerate(ITEMS):
        if item.id == item_id:
            ITEMS.pop(i)
            return Response(status_code=204)
    return JSONResponse(
        status_code=404,
        content=ErrorResponse(code=404, message="Item not found").model_dump(),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
