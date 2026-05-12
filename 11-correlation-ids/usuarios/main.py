import logging
import os
import uuid
from contextvars import ContextVar

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Path, Request
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

# ContextVar almacena el correlation ID de forma aislada por cada request (hilo o tarea asyncio).
# El valor por defecto se usa si se emite algún log fuera del ciclo de vida de un request.
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")


# Filtro de logging que inyecta el correlation ID en cada registro antes de emitirlo.
# Al heredar de logging.Filter, se integra directamente con la infraestructura estándar de Python.
class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Lee el valor actual del ContextVar y lo añade como atributo del registro.
        # Esto hace que %(correlation_id)s esté disponible en el formato del handler.
        record.correlation_id = correlation_id_var.get()
        return True


# Configura el logging raíz con un formato que incluye el correlation ID entre corchetes.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s cid=[%(correlation_id)s] %(levelname)s %(name)s - %(message)s",
)

# Aplica el filtro a todos los handlers del logger raíz para que todos los mensajes
# de la aplicación (y librerías que usen el logger raíz) incluyan el correlation ID.
for _handler in logging.root.handlers:
    _handler.addFilter(CorrelationIdFilter())

logger = logging.getLogger(__name__)


# Devuelve los headers que deben incluirse en toda llamada a servicios downstream.
# Centraliza la propagación del correlation ID para no repetir la lógica en cada endpoint.
def downstream_headers() -> dict[str, str]:
    return {"X-Correlation-ID": correlation_id_var.get()}


load_dotenv("config.env")

libros_service = os.getenv("LIBROS_SERVICE")
database_url = os.getenv("DATABASE_URL")

engine = create_engine(database_url)


class Base(DeclarativeBase):
    pass


class UserRecord(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)


class UserBook(Base):
    __tablename__ = "user_books"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    book_id = Column(Integer, nullable=False)


Base.metadata.create_all(engine)


app = FastAPI(
    title="Users API",
    description="API para listar usuarios.",
    version="1.0.0",
)


# Middleware HTTP que intercepta cada request antes de que llegue a los endpoints.
# Su responsabilidad es establecer el correlation ID para todo el ciclo de vida del request.
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    # Intenta leer el correlation ID del header enviado por el cliente o sistema upstream.
    # Si no existe, genera uno nuevo con UUID v4 para garantizar unicidad global.
    correlation_id = request.headers.get(
        "X-Correlation-ID") or str(uuid.uuid4())

    # Establece el valor en el ContextVar. El token permite restaurar el estado anterior
    # al finalizar el request, lo cual es importante en entornos con requests concurrentes.
    token = correlation_id_var.set(correlation_id)
    try:
        response = await call_next(request)
        # Propaga el correlation ID en el header de la respuesta para que el cliente
        # (u otro servicio) pueda correlacionar la respuesta con su request original.
        response.headers["X-Correlation-ID"] = correlation_id
        return response
    finally:
        # Restaura el ContextVar a su valor previo al terminar el request,
        # liberando el estado para futuros requests que reutilicen el mismo contexto.
        correlation_id_var.reset(token)


# Modelo que representa un usuario en esta API
class User(BaseModel):
    # ... El campo 'id' es obligatorio (Field(...)) y tiene una descripción para la documentación automática
    id: int = Field(..., description="Identificador único del usuario")
    first_name: str = Field(..., description="Nombre del usuario")
    last_name: str = Field(..., description="Apellido del usuario")
    email: str = Field(..., description="Correo electrónico del usuario")


# Modelo que representa un libro devuelto por el servicio externo
class Book(BaseModel):
    id: int
    titulo: str
    autor: str


class NewBookRequest(BaseModel):
    autor_nombre: str = Field(..., description="Nombre del autor del libro")
    titulo: str = Field(..., description="Título del libro")


class CreatedBook(BaseModel):
    id: int
    titulo: str
    autor_id: int


@app.get(
    "/libros/{libro_id}",
    response_model=Book,
    summary="Obtener libro",
    description="Consulta un libro por ID en el servicio externo.",
    tags=["Libros"],
    responses={404: {"description": "Libro no encontrado"}},
)
def get_libro(libro_id: int = Path(..., description="Identificador del libro")) -> Book:
    logger.info("Fetching book libro_id=%d", libro_id)
    response = requests.get(
        f"{libros_service}/libros/{libro_id}", headers=downstream_headers())

    if response.status_code == 404:
        logger.warning("Book not found libro_id=%d", libro_id)
        raise HTTPException(status_code=404, detail="Libro no encontrado")

    book = Book(**response.json())
    logger.info("Book retrieved libro_id=%d titulo=%s", libro_id, book.titulo)
    return book


@app.get(
    "/users/{user_id}/books",
    response_model=list[Book],
    summary="Libros de un usuario",
    description="Devuelve entre 1 y 3 libros aleatorios asociados al usuario.",
    tags=["Users"],
)
def get_user_books(user_id: int = Path(..., description="Identificador del usuario")) -> list[Book]:
    logger.info("Fetching books for user_id=%d", user_id)
    with Session(engine) as session:
        user = session.get(UserRecord, user_id)
        if user is None:
            logger.warning("User not found user_id=%d", user_id)
            raise HTTPException(
                status_code=404, detail="Usuario no encontrado")
        book_ids = [ub.book_id for ub in session.query(
            UserBook).filter(UserBook.user_id == user_id).all()]

    logger.info("Found book_ids=%s for user_id=%d", book_ids, user_id)

    books = []
    for book_id in book_ids:
        response = requests.get(
            f"{libros_service}/libros/{book_id}", headers=downstream_headers())
        if response.status_code == 200:
            books.append(Book(**response.json()))
        else:
            logger.warning("Could not fetch book_id=%d status=%d",
                           book_id, response.status_code)

    logger.info("Returning %d books for user_id=%d", len(books), user_id)
    return books


@app.get(
    "/users",
    response_model=list[User],
    summary="Listar usuarios",
    description="Devuelve la lista completa de usuarios.",
    tags=["Users"],
)
def list_users() -> list[User]:
    with Session(engine) as session:
        records = session.query(UserRecord).all()
    users = [User(id=r.id, first_name=r.first_name,
                  last_name=r.last_name, email=r.email) for r in records]
    logger.info("Listing all users count=%d", len(users))
    return users


@app.put(
    "/users/{user_id}/books",
    response_model=CreatedBook,
    status_code=201,
    summary="Agregar libro a usuario",
    description="Crea un nuevo libro en el servicio de libros y lo asocia al usuario.",
    tags=["Users"],
    responses={
        404: {"description": "Usuario no encontrado"},
        502: {"description": "Error al crear el libro en el servicio externo"},
    },
)
def add_book_to_user(
    payload: NewBookRequest,
    user_id: int = Path(..., description="Identificador del usuario"),
) -> CreatedBook:
    logger.info("Adding book for user_id=%d titulo=%s",
                user_id, payload.titulo)
    with Session(engine) as session:
        user = session.get(UserRecord, user_id)
    if user is None:
        logger.warning("User not found user_id=%d", user_id)
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    response = requests.post(
        f"{libros_service}/libros",
        json={"autor_nombre": payload.autor_nombre, "titulo": payload.titulo},
        headers=downstream_headers(),
    )

    if response.status_code != 201:
        logger.error(
            "Failed to create book for user_id=%d status=%d body=%s",
            user_id, response.status_code, response.text,
        )
        raise HTTPException(
            status_code=502, detail="Error al crear el libro en el servicio externo")

    created = CreatedBook(**response.json())
    with Session(engine) as session:
        session.add(UserBook(user_id=user_id, book_id=created.id))
        session.commit()
    logger.info("Book created book_id=%d for user_id=%d", created.id, user_id)
    return created


# Para correr python main.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
