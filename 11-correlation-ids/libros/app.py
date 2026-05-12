import os
import uuid
import logging

from flask import Flask, jsonify, request, g
from flasgger import Swagger
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import DeclarativeBase, Session

load_dotenv("config.env")


# ──────────────────────────────────────────────
# Filtro de logging: inyecta el correlation_id
# en cada registro de log de forma centralizada.
# ──────────────────────────────────────────────
class CorrelationIdFilter(logging.Filter):
    """Agrega el atributo correlation_id a cada LogRecord."""

    def filter(self, record):
        # flask.g existe solo dentro de un contexto de petición HTTP.
        # Si el log ocurre fuera de ese contexto (arranque, tareas, etc.)
        # usamos "N/A" como valor por defecto para no romper el formato.
        try:
            record.correlation_id = g.correlation_id
        except RuntimeError:
            record.correlation_id = "N/A"
        return True


# Incluimos %(correlation_id)s en el formato para que aparezca en cada línea.
# El filtro debe ir en el HANDLER, no en el logger.  Cuando app.logger (logger
# hijo) propaga un registro al logger raíz, Python invoca los handlers del
# padre directamente sin pasar por los filtros del logger padre.  Los filtros
# del handler sí se evalúan siempre, por eso es el lugar correcto.
_correlation_filter = CorrelationIdFilter()
_stream_handler = logging.StreamHandler()
# logging.FileHandler("app.log")
_stream_handler.addFilter(_correlation_filter)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - cid-[%(correlation_id)s] - %(message)s",
    handlers=[_stream_handler]
)

app = Flask(__name__)

swagger_template = {
    "info": {
        "title": "API de Libros",
        "version": "1.0",
        "description": "Para manejar libros.",
        "termsOfService": "https://www.lospatitos.com/tos/",
        "contact": {
            "responsibleOrganization": "Los Patitos",
            "responsibleDeveloper": "Patito",
            "email": "patito@lospatitos.com",
            "url": "https://www.lospatitos.com",
        },
    }
}
swagger = Swagger(app, template=swagger_template)

engine = create_engine(os.getenv("DATABASE_URL"))


class Base(DeclarativeBase):
    pass


class Libro(Base):
    __tablename__ = "libros"
    id = Column(Integer, primary_key=True, autoincrement=True)
    titulo = Column(String, nullable=False)
    autor_id = Column(Integer, nullable=False)


Base.metadata.create_all(engine)


# ──────────────────────────────────────────────
# Hook que se ejecuta antes de cada petición.
# Centraliza la lógica de obtener/crear el
# correlation_id y guardarlo en flask.g para
# que esté disponible en todo el ciclo de vida
# de la petición (logs, llamadas downstream, etc.)
# ──────────────────────────────────────────────
@app.before_request
def set_correlation_id():
    # Si el cliente envía el header lo reutilizamos; de lo contrario
    # generamos un UUID nuevo para rastrear la petición internamente.
    correlation_id = request.headers.get(
        "X-Correlation-ID") or str(uuid.uuid4())
    g.correlation_id = correlation_id


@app.route('/libros/<int:libro_id>', methods=['GET'])
def get_libro(libro_id):
    """
    Obtener libro por ID
    ---
    parameters:
      - name: libro_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Libro encontrado
        schema:
          id: Libro
          properties:
            id:
              type: integer
            titulo:
              type: string
            autor:
              type: string
      404:
        description: Libro no encontrado
        schema:
          id: Error
          properties:
            error:
              type: string
    """
    libro = find_book(libro_id)
    if libro:
        app.logger.info("Libro con id %d encontrado", libro_id)
        return jsonify(libro), 200
    app.logger.info("Libro con id %d NO encontrado", libro_id)
    return jsonify({"error": "Libro no encontrado"}), 404


def find_book(libro_id):
    with Session(engine) as session:
        libro = session.get(Libro, libro_id)
        if libro:
            autor = find_author_from_book(libro.autor_id)
            return {
                "id": libro.id,
                "titulo": libro.titulo,
                "autor": autor["nombre"] if autor else "Desconocido",
            }
    return None


def create_author(nombre):
    autores_service = os.getenv("AUTORES_SERVICE")
    graphql_url = f"{autores_service}/graphql"

    app.logger.info("Creando autor '%s' en servicio: %s", nombre, graphql_url)

    mutation = """
    mutation MyMutation {
      crearAutor(nombre: "%s") {
        id
        nombre
      }
    }
    """ % nombre

    headers = {"X-Correlation-ID": g.correlation_id}

    response = requests.post(
        graphql_url, json={"query": mutation}, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data.get("data", {}).get("crearAutor")
    return None


@app.route('/libros', methods=['POST'])
def create_libro():
    """
    Crear un nuevo libro
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            titulo:
              type: string
            autor_nombre:
              type: string
    responses:
      201:
        description: Libro creado
        schema:
          id: LibroCreado
          properties:
            id:
              type: integer
            titulo:
              type: string
            autor_id:
              type: integer
      400:
        description: Datos inválidos
      502:
        description: Error creando autor en servicio externo
    """
    body = request.get_json()
    titulo = body.get("titulo")
    autor_nombre = body.get("autor_nombre")

    if not titulo or not autor_nombre:
        return jsonify({"error": "titulo y autor_nombre son requeridos"}), 400

    autor = create_author(autor_nombre)
    if not autor:
        app.logger.error("No se pudo crear el autor '%s'", autor_nombre)
        return jsonify({"error": "Error al crear el autor en el servicio externo"}), 502

    with Session(engine) as session:
        nuevo = Libro(titulo=titulo, autor_id=autor["id"])
        session.add(nuevo)
        session.commit()
        session.refresh(nuevo)
        app.logger.info("Libro creado con id %d, autor_id %d",
                        nuevo.id, nuevo.autor_id)
        return jsonify({"id": nuevo.id, "titulo": nuevo.titulo, "autor_id": nuevo.autor_id}), 201


def find_author_from_book(autor_id):
    autores_service = os.getenv("AUTORES_SERVICE")
    graphql_url = f"{autores_service}/graphql"

    app.logger.info("Servicio de autores (GraphQL): %s", graphql_url)

    query = """
    query MyQuery {
      autor(autorId: %s) {
        id
        nombre
      }
    }
    """ % autor_id

    # Propagamos el correlation_id al servicio downstream para que
    # todos los servicios involucrados en la petición compartan el
    # mismo identificador y sea fácil correlacionar logs entre ellos.
    headers = {"X-Correlation-ID": g.correlation_id}

    response = requests.post(
        graphql_url, json={"query": query}, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data.get("data", {}).get("autor")
    return None


if __name__ == '__main__':
    app.run(debug=True, port=5001)
