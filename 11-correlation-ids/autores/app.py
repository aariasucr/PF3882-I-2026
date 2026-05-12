import os
import uuid
import logging

from flask import Flask, g, request
import strawberry
from strawberry.flask.views import GraphQLView
from typing import Optional
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import DeclarativeBase, Session

load_dotenv("config.env")


engine = create_engine(os.environ["DATABASE_URL"])


class Base(DeclarativeBase):
    pass


class AutorModel(Base):
    __tablename__ = "autores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String, nullable=False)


Base.metadata.create_all(engine)


# ──────────────────────────────────────────────────────────────────────────────
# Filtro de logging: inyecta el correlation_id en cada registro de log.
#
# El filtro va en el HANDLER (no en el logger padre).  Cuando app.logger
# (logger hijo) propaga un registro al logger raíz, Python llama directamente
# a los handlers del padre sin evaluar los filtros del logger raíz.
# Los filtros del handler sí se evalúan siempre, por eso es el lugar correcto.
# ──────────────────────────────────────────────────────────────────────────────
class CorrelationIdFilter(logging.Filter):
    """Agrega el atributo correlation_id a cada LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        # flask.g solo existe dentro de un contexto de petición HTTP.
        # Fuera de él (arranque, tareas en background, etc.) usamos "N/A"
        # para no romper el formato del mensaje.
        try:
            record.correlation_id = g.correlation_id
        except RuntimeError:
            record.correlation_id = "N/A"
        return True


# Creamos el handler con su filtro y formato una sola vez (centralizado).
# Todos los loggers de la aplicación heredan este handler del logger raíz.
_handler = logging.StreamHandler()
_handler.addFilter(CorrelationIdFilter())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - cid-[%(correlation_id)s] - %(message)s",
    handlers=[_handler],
)

app = Flask(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Hook que se ejecuta ANTES de cada petición HTTP entrante.
# Centraliza la lógica de obtener o generar el Correlation ID.
# ──────────────────────────────────────────────────────────────────────────────
@app.before_request
def set_correlation_id() -> None:
    # Si el cliente (o el servicio upstream) ya envía el header, lo reutilizamos
    # para mantener la traza end-to-end.  Si no viene, generamos un UUID nuevo.
    incoming = request.headers.get("X-Correlation-ID")
    g.correlation_id = incoming if incoming else str(uuid.uuid4())
    app.logger.info(
        "Petición recibida — correlation_id: %s (origen: %s)",
        g.correlation_id,
        "header entrante" if incoming else "generado",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Hook que se ejecuta DESPUÉS de cada petición HTTP.
# Devuelve el Correlation ID en la respuesta para que el cliente pueda
# correlacionar su petición con los logs del servidor.
# ──────────────────────────────────────────────────────────────────────────────
@app.after_request
def attach_correlation_id(response):
    response.headers["X-Correlation-ID"] = g.correlation_id
    return response


# ──────────────────────────────────────────────────────────────────────────────
# Función centralizada para propagar el Correlation ID a servicios downstream.
# Cualquier llamada HTTP saliente debe incluir estos headers para que todos
# los servicios de la cadena compartan el mismo identificador de traza.
# ──────────────────────────────────────────────────────────────────────────────
def downstream_headers() -> dict:
    """Retorna los headers necesarios para propagar el Correlation ID."""
    return {"X-Correlation-ID": g.correlation_id}


@strawberry.type
class Autor:
    id: int
    nombre: str


@strawberry.type
class Query:
    @strawberry.field
    def autores(self) -> list[Autor]:
        with Session(engine) as session:
            rows = session.query(AutorModel).all()
        app.logger.info(
            "Retornando lista de autores con tamaño: %d", len(rows))
        return [Autor(id=r.id, nombre=r.nombre) for r in rows]

    @strawberry.field
    def autor(self, autor_id: int) -> Optional[Autor]:
        with Session(engine) as session:
            row = session.get(AutorModel, autor_id)
        if row:
            app.logger.info("Autor con id %d encontrado", autor_id)
            return Autor(id=row.id, nombre=row.nombre)
        app.logger.info("Autor con id %d NO encontrado", autor_id)
        return None


@strawberry.type
class Mutation:
    @strawberry.mutation
    def crear_autor(self, nombre: str) -> Autor:
        with Session(engine) as session:
            nuevo = AutorModel(nombre=nombre)
            session.add(nuevo)
            session.commit()
            session.refresh(nuevo)
            app.logger.info("Autor creado con id %d", nuevo.id)
            return Autor(id=nuevo.id, nombre=nuevo.nombre)


schema = strawberry.Schema(query=Query, mutation=Mutation)

app.add_url_rule(
    "/graphql",
    view_func=GraphQLView.as_view("graphql_view", schema=schema),
)


if __name__ == "__main__":
    app.run(debug=True, port=5002)
