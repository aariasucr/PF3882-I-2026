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
    """
    Callback invoked by Pika each time a message is delivered from RabbitMQ.

    Args:
        ch:         Channel object through which the message was received.
        method:     Delivery metadata such as the routing key and delivery tag.
        properties: Message properties (headers, content-type, etc.).
        body:       Raw message payload as bytes.
    """
    # Decode the binary payload to a UTF-8 string and log it
    logging.info(
        f"Llego esto de rabbitmq: {body.decode()} - Routing Key: {method.routing_key}  - Delivery Tag: {method.delivery_tag}")


load_dotenv("config.env")
rabbitmq_host = os.getenv("RABBITMQ_HOST")


# connection = pika.BlockingConnection(pika.ConnectionParameters(rabbitmq_host))
# channel = connection.channel()
# channel.queue_declare(queue='cola-de-libros')

# channel.basic_consume(
#     queue='cola-de-libros', on_message_callback=callback_rabbitmq, auto_ack=True)
# logging.info("Esperando mensajes...")
# channel.start_consuming()

while True:
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(rabbitmq_host))
        channel = connection.channel()
        channel.exchange_declare(
            exchange='libros-topic', exchange_type='topic')
        result = channel.queue_declare(queue='', exclusive=True)
        queue_name = result.method.queue
        channel.queue_bind(exchange='libros-topic',
                           queue=queue_name, routing_key='books.fiction.*')
        channel.basic_consume(
            queue=queue_name, on_message_callback=callback_rabbitmq, auto_ack=True)
        logging.info("Esperando mensajes...")
        channel.start_consuming()
    except pika.exceptions.AMQPConnectionError as e:
        logging.warning(
            f"No se pudo conectar a RabbitMQ: {e}. Reintentando en 5 segundos...")
        time.sleep(5)
