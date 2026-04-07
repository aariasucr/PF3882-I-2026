from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

app = FastAPI(title="Basic REST API")


class Item(BaseModel):
    id: int
    name: str
    description: str | None = None


class ItemCreate(BaseModel):
    name: str
    description: str | None = None


class ItemUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ErrorResponse(BaseModel):
    code: int
    message: str


ITEMS: list[Item] = [
    Item(id=1, name="Monitor", description="Un monitor de 24 pulgadas"),
    Item(id=2, name="Keyboard", description="Un teclado mecânico"),
    Item(id=3, name="Mouse", description="Un mouse óptico"),
]


@app.get("/")
def root():
    return {"message": "Welcome to the Basic REST API"}


@app.get("/items", response_model=list[Item])
def list_items() -> list[Item]:
    return ITEMS


@app.get("/items/{item_id}", response_model=Item)
def get_item(item_id: int) -> Item:
    for item in ITEMS:
        if item.id == item_id:
            return item
    raise HTTPException(status_code=404, detail="Item not found")


@app.post("/items", response_model=Item, status_code=201)
def create_item(body: ItemCreate) -> Item:
    next_id = max((i.id for i in ITEMS), default=0) + 1
    item = Item(id=next_id, name=body.name, description=body.description)
    ITEMS.append(item)
    return item


@app.put("/items/{item_id}", response_model=Item)
def update_item(item_id: int, body: ItemUpdate) -> Item:
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


@app.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int) -> None:
    for i, item in enumerate(ITEMS):
        if item.id == item_id:
            ITEMS.pop(i)
            return
    raise HTTPException(status_code=404, detail="Item not found")


@app.delete(
    "/items/otrodelete/{item_id}",
    response_model=None,
    responses={
        204: {"description": "Item borrado"},
        404: {"description": "Item no encontrado", "model": ErrorResponse},
    }
)
def otro_delete_item(item_id: int) -> Response | JSONResponse:
    for i, item in enumerate(ITEMS):
        if item.id == item_id:
            ITEMS.pop(i)
            return Response(status_code=204)
    return JSONResponse(
        status_code=404,
        content=ErrorResponse(
            code=404, message="Item no encontrado").model_dump(),
    )


# Para correr python main.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
