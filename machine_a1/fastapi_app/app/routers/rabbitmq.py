import asyncio
import aio_pika
import json
import logging
from app.sql import crud
from app.routers import rabbitmq_publish_logs
import ssl
import logging
from global_variables.global_variables import update_system_resources_periodically, set_rabbitmq_status, get_rabbitmq_status


logger = logging.getLogger(__name__)

# Configuración SSL
ssl_context = ssl.create_default_context(cafile="/keys/ca_cert.pem")
ssl_context.check_hostname = False  # Deshabilita la verificación del hostname
ssl_context.verify_mode = ssl.CERT_NONE  # No verifica el certificado del servidor

# Variables globales
channel = None
exchange = None
exchange_name = 'events'

async def subscribe_channel():
    """
    Conéctate a RabbitMQ utilizando SSL, declara los intercambios necesarios y configura el canal.
    """
    global channel, exchange, exchange_name

    try:
        logger.info("Intentando suscribirse...")

        # Establece la conexión robusta con RabbitMQ
        connection = await aio_pika.connect_robust(
            host='rabbitmq',
            port=5671,  # Puerto seguro SSL
            virtualhost='/',
            login='guest',
            password='guest',
            ssl=True,
            ssl_context=ssl_context
        )
        logger.info("Conexión establecida con éxito")

        # Crear un canal
        channel = await connection.channel()
        logger.debug("Canal creado con éxito")

        # Declarar el intercambio específico
        exchange = await channel.declare_exchange(
            name=exchange_name,
            type='topic',
            durable=True
        )
        rabbitmq_working = True
        set_rabbitmq_status(True)
        logger.info("rabbitmq_working : " + str(rabbitmq_working))
        logger.info(f"Intercambio '{exchange_name}' declarado con éxito")
        await channel.set_qos(1)

    except Exception as e:
        logger.error(f"Error durante la suscripción: {e}")
        raise  # Propaga el error para manejo en niveles superiores


async def on_message(message):
    async with message.process():
        try:
            piece = json.loads(message.body)
            logger.debug(f"Received piece request: {piece}")

            await crud.set_status_of_machine("Machine Status: Producing")
            await asyncio.sleep(3)

            logger.info(f"Piece A produced: {piece['id_piece']}")
            await crud.set_status_of_machine("Machine Status: Idle")

            data = {"id_piece": piece['id_piece']}
            message_body = json.dumps(data)
            routing_key = "piece.produced"

            logger.debug(f"Publishing message: {message_body} to routing key: {routing_key}")
            await publish(message_body, routing_key)
            logger.debug("Message published successfully.")
        except Exception as e:
            logger.error(f"Error in on_message: {e}")



async def subscribe():
    # Create queue
    queue_name = "piece_a.requested"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "piece_a.requested"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_message(message)


async def publish(message_body, routing_key):
    logger.info("Intentando publicar mensaje con routing_key: %s", routing_key)
    await exchange.publish(
        aio_pika.Message(
            body=message_body.encode(),
            content_type="text/plain"
        ),
        routing_key=routing_key
    )
    logger.info("Mensaje publicado con éxito")

