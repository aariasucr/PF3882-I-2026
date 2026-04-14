from flask import Flask, jsonify, request
from flasgger import Swagger
import pika
from dotenv import load_dotenv
import os
import logging

app = Flask(__name__)
swagger = Swagger(app)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        # logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)


load_dotenv("config.env")


def publish_message(routing_key, data):
    rabbitmq_host = os.getenv("RABBITMQ_HOST")
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(rabbitmq_host))
    channel = connection.channel()
    channel.exchange_declare(exchange='libros-topic', exchange_type='topic')
    channel.basic_publish(exchange='libros-topic', routing_key=routing_key,
                          body=str(data))
    connection.close()
    app.logger.info("Mensaje enviado con routing_key '%s': %s",
                    routing_key, data)


@app.route('/books/all', methods=['GET'])
def books_all():
    """
    Mandar mensaje al topic "books.#"
    ---
    responses:
      200:
        description: Mensaje enviado a books.#
    """
    data = {'title': 'Cien años de soledad',
            'author': 'Gabriel García Márquez'}
    publish_message('books.#', data)
    return jsonify("Mensaje enviado con routing_key 'books.all'"), 200


@app.route('/books/fiction', methods=['GET'])
def books_fiction():
    """
    Mandar mensaje al topic "books.fiction.*"
    ---
    responses:
      200:
        description: Mensaje enviado a books.fiction.*
    """
    data = {'title': 'Dune', 'author': 'Frank Herbert'}
    publish_message('books.fiction.*', data)
    return jsonify("Mensaje enviado con routing_key 'books.fiction.*'"), 200


@app.route('/books/fiction/spanish', methods=['GET'])
def books_fiction_spanish():
    """
    Mandar mensaje al topic "books.fiction.spanish"
    ---
    responses:
      200:
        description: Mensaje enviado a books.fiction.spanish
    """
    data = {'title': 'La sombra del viento', 'author': 'Carlos Ruiz Zafón'}
    publish_message('books.fiction.spanish', data)
    return jsonify("Mensaje enviado con routing_key 'books.fiction.spanish'"), 200


# Iniciar la aplicación
if __name__ == '__main__':
    app.run(debug=True)
