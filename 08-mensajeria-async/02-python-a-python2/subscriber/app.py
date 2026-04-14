from flask import Flask, jsonify, request
from flasgger import Swagger

import pika
from dotenv import load_dotenv
import os
import logging
import time
import threading

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


@app.route('/ech0', methods=['GET'])
def echo():
    """
    Echo endpoint
    ---
    responses:
      200:
        description: Returns the echoed message
        content:
          application/json:
            schema:
              type: object
              properties:
                message:
                  type: string
                  example: "Hello, World!"
    """
    return jsonify({"mensaje": "Hola!"})


def callback_rabbitmq(ch, method, properties, body):
    logging.info(f"Llego esto de rabbitmq: {body.decode()}")


rabbitmq_host = os.getenv("RABBITMQ_HOST")


# connection = pika.BlockingConnection(pika.ConnectionParameters(rabbitmq_host))
# channel = connection.channel()
# channel.queue_declare(queue='cola-de-libros')

# channel.basic_consume(
#     queue='cola-de-libros', on_message_callback=callback_rabbitmq, auto_ack=True)
# logging.info("Esperando mensajes...")
# channel.start_consuming()

def rabbitmq_consumer():
    while True:
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(rabbitmq_host))
            channel = connection.channel()
            channel.queue_declare(queue='cola-de-libros')
            channel.basic_consume(
                queue='cola-de-libros', on_message_callback=callback_rabbitmq, auto_ack=True)
            logging.info("Esperando mensajes...")
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError as e:
            logging.warning(
                f"No se pudo conectar a RabbitMQ: {e}. Reintentando en 5 segundos...")
            time.sleep(5)


if __name__ == '__main__':
    # Iniciar el consumidor de RabbitMQ en un hilo separado
    consumer_thread = threading.Thread(target=rabbitmq_consumer, daemon=True)
    consumer_thread.start()
    app.run(debug=True, host='0.0.0.0', port=5001)
