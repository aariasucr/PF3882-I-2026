import pika
from dotenv import load_dotenv
import os
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        # logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)


def callback_rabbitmq(ch, method, properties, body):
    # Callback para procesar mensajes recibidos de RabbitMQ
    logging.info(f"Llego esto de rabbitmq: {body.decode()}")


load_dotenv("config.env")
rabbitmq_host = os.getenv("RABBITMQ_HOST")


# Conexión a RabbitMQ y consumo de mensajes - falla si RabbitMQ no está disponible al iniciar el consumidor
# connection = pika.BlockingConnection(pika.ConnectionParameters(rabbitmq_host))
# channel = connection.channel()
# channel.queue_declare(queue='cola-de-libros')
# channel.basic_consume(
#     queue='cola-de-libros', on_message_callback=callback_rabbitmq, auto_ack=True)
# logging.info("Esperando mensajes...")
# channel.start_consuming()

# Para manejar reconexiones automáticas a RabbitMQ en caso de que el servicio no esté disponible al iniciar el consumidor
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
