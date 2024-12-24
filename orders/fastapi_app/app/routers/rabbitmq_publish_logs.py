import aio_pika
import json
import ssl
import logging
from app.sql.database import SessionLocal # pylint: disable=import-outside-toplevel


# Configuración del logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración del contexto SSL
ssl_context = ssl.create_default_context(cafile="/keys/ca_cert.pem")
ssl_context.check_hostname = False  # Deshabilita la verificación del hostname
ssl_context.verify_mode = ssl.CERT_NONE  # No verifica el certificado del servidor

# Variables globales
channel = None
exchange_logs_name = 'exchange'
exchange_logs = None

async def subscribe_channel():
    """
    Conéctate a RabbitMQ utilizando SSL, declara los intercambios necesarios y configura el canal.
    """
    global channel, exchange_logs, exchange_logs_name

    try:
        logger.info("Intentando conectarse a RabbitMQ...")

        # Establece la conexión robusta con RabbitMQ
        connection = await aio_pika.connect_robust(
            host='rabbitmq',
            port=5671,
            virtualhost='/',
            login='guest',
            password='guest',
            ssl=True,
            ssl_context=ssl_context
        )
        logger.info("Conexión establecida con éxito")

        # Crear un canal
        channel = await connection.channel()
        logger.info("Canal creado con éxito")

        # Declarar el intercambio
        exchange_logs = await channel.declare_exchange(
            name=exchange_logs_name,
            type='topic',
            durable=True
        )
        logger.info(f"Intercambio '{exchange_logs_name}' declarado con éxito")

    except Exception as e:
        logger.error(f"Error al suscribirse: {e}")
        raise  # Re-lanzar el error para manejo superior si es necesari


async def publish_log(message_body, routing_key):
    # Publish the message to the exchange
    await exchange_logs.publish(
        aio_pika.Message(
            body=message_body.encode(),
            content_type="text/plain"
        ),
        routing_key=routing_key)