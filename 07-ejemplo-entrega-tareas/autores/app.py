from flask import Flask
import strawberry
from strawberry.flask.views import GraphQLView
import logging
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        # logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

app = Flask(__name__)

autores_data = [
    {"id": 1, "nombre": "George Orwell"},
    {"id": 2, "nombre": "Isabel Allende"},
    {"id": 3, "nombre": "Aquileo Echeverría"},
    {"id": 4, "nombre": "J.D. Salinger"},
    {"id": 5, "nombre": "Carlos Salazar"},
    {"id": 6, "nombre": "F. Scott Fitzgerald"},
    {"id": 7, "nombre": "Gabriel García Márquez"}
]


@strawberry.type
class Autor:
    id: int
    nombre: str


@strawberry.type
class Query:
    @strawberry.field
    def autores(self) -> list[Autor]:
        app.logger.info(
            "Retornando lista de autores con tamaño: %d", len(autores_data))
        return [Autor(id=a["id"], nombre=a["nombre"]) for a in autores_data]

    @strawberry.field
    def autor(self, autor_id: int) -> Optional[Autor]:
        for a in autores_data:
            if a["id"] == autor_id:
                app.logger.info("Autor con id %d encontrado", autor_id)
                return Autor(id=a["id"], nombre=a["nombre"])
        app.logger.info("Autor con id %d NO encontrado", autor_id)
        return None

    @strawberry.field
    def autor_by_name(self, nombre: str) -> list[Autor]:
        resultados = []
        for a in autores_data:
            if nombre in a["nombre"]:
                app.logger.info("Autor con nombre %s encontrado", nombre)
                resultados.append(Autor(id=a["id"], nombre=a["nombre"]))
        if not resultados:
            app.logger.info("Autor con nombre %s NO encontrado", nombre)
        return resultados


schema = strawberry.Schema(query=Query)

app.add_url_rule(
    "/graphql",
    view_func=GraphQLView.as_view("graphql_view", schema=schema),
)


if __name__ == '__main__':
    app.run(debug=True, port=5002)
