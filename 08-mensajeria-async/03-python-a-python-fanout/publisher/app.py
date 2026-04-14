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


@app.route('/rabbitmq', methods=['GET'])
def rabbitmq():
    """
    Mandar mensaje a RabbitMQ
    ---
    responses:
      200:
        description: Mensaje enviado
    """

    data = {}
    data['title'] = "Cien años de soledad"
    data['author'] = "Gabriel García Márquez"

    rabbitmq_host = os.getenv("RABBITMQ_HOST")

    # Conectarse a RabbitMQ
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(rabbitmq_host))

    # Crear un canal
    channel = connection.channel()

    # Declarar un exchange de tipo fanout para broadcast
    channel.exchange_declare(exchange='libros-fanout', exchange_type='fanout')

    # Publicar un mensaje al exchange (sin routing_key, fanout la ignora)
    channel.basic_publish(exchange='libros-fanout', routing_key='',
                          body=str(data))
    # Cerrar la conexión
    connection.close()
    app.logger.info("Mensaje enviado al exchange fanout: %s", data)

    return jsonify("Mensaje enviado a RabbitMQ"), 200


# Iniciar la aplicación
if __name__ == '__main__':
    app.run(debug=True)
