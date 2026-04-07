import os
import random
import requests
from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel, Field

from dotenv import load_dotenv

load_dotenv("config.env")

libros_service = os.getenv("LIBROS_SERVICE")


app = FastAPI(
    title="Users API",
    description="API para listar usuarios.",
    version="1.0.0",
)


# Modelo que representa un usuario en esta API
class User(BaseModel):
    # ... El campo 'id' es obligatorio (Field(...)) y tiene una descripción para la documentación automática
    id: int = Field(..., description="Identificador único del usuario")
    first_name: str = Field(..., description="Nombre del usuario")
    last_name: str = Field(..., description="Apellido del usuario")
    email: str = Field(..., description="Correo electrónico del usuario")


# Lista en memoria que simula la base de datos de usuarios
USERS: list[User] = [
    User(id=1, first_name="Ana", last_name="García",
         email="ana.garcia@example.com"),
    User(id=2, first_name="Carlos", last_name="Pérez",
         email="carlos.perez@example.com"),
    User(id=3, first_name="María", last_name="López",
         email="maria.lopez@example.com"),
]


# Modelo que representa un libro devuelto por el servicio externo
class Book(BaseModel):
    id: int
    titulo: str
    autor: str


@app.get(
    "/libros/{libro_id}",
    response_model=Book,
    summary="Obtener libro",
    description="Consulta un libro por ID en el servicio externo.",
    tags=["Libros"],
    responses={404: {"description": "Libro no encontrado"}},
)
def get_libro(libro_id: int = Path(..., description="Identificador del libro")) -> Book:
    # Llama al servicio externo de libros con el ID recibido
    response = requests.get(f"{libros_service}/libros/{libro_id}")

    # Si el servicio externo responde 404, lo propagamos al cliente
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Libro no encontrado")

    # response.json() convierte el cuerpo de la respuesta en un dict de Python,
    # y ** lo desempaca como argumentos nombrados para construir el objeto Book.
    # Equivale a: Book(id=..., titulo=..., autor=...)
    return Book(**response.json())


@app.get(
    "/users/{user_id}/books",
    response_model=list[Book],
    summary="Libros de un usuario",
    description="Devuelve entre 1 y 3 libros aleatorios asociados al usuario.",
    tags=["Users"],
)
def get_user_books(user_id: int = Path(..., description="Identificador del usuario")) -> list[Book]:
    # Verificar que el usuario existe
    user = next((u for u in USERS if u.id == user_id), None)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Seleccionar entre 1 y 3 IDs únicos al azar del rango 1-7
    count = random.randint(1, 3)
    book_ids = random.sample(range(1, 8), count)

    # Llamar al servicio externo por cada ID y recolectar los libros
    books = []
    for book_id in book_ids:
        response = requests.get(f"{libros_service}/libros/{book_id}")
        if response.status_code == 200:
            books.append(Book(**response.json()))

    return books


@app.get(
    "/users",
    response_model=list[User],
    summary="Listar usuarios",
    description="Devuelve la lista completa de usuarios.",
    tags=["Users"],
)
def list_users() -> list[User]:
    # Devuelve todos los usuarios almacenados en memoria
    return USERS


# Para correr python main.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
