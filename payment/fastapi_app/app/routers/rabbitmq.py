import aio_pika
import json
import ssl
import logging
from os import environ
from app.sql.database import SessionLocal  # pylint: disable=import-outside-toplevel
from app.sql import crud, models
from global_variables.global_variables import update_system_resources_periodically, set_rabbitmq_status, get_rabbitmq_status, system_values
from fastapi.responses import JSONResponse


# Configura el logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ssl_context = ssl.create_default_context(cafile="/keys/ca_cert.pem")
ssl_context.check_hostname = False  # Deshabilita la verificación del hostname
ssl_context.verify_mode = ssl.CERT_NONE  # No verifica el certificado del servidor

channel = None
exchange_commands = None
exchange_events = None
exchange_commands_name = 'commands'
exchange_events_name = 'events'
exchange_responses_name = 'responses'
exchange_responses = None

async def subscribe_channel():
    global channel, exchange_commands, exchange_events, exchange_commands_name, exchange_events_name, exchange_responses, exchange_responses_name
    try:
        logger.info("Intentando suscribirse...")
        connection = await aio_pika.connect_robust(
            host=environ.get("RABBITMQ_HOST"),
            port=int(environ.get("RABBITMQ_PORT_SERVICE")),  # Puerto seguro SSL
            virtualhost='/',
            login='guest',
            password='guest',
            ssl=True,
            ssl_context=ssl_context
        )
        logger.info("Conexión establecida con éxito")
        # Create a channel
        channel = await connection.channel()
        logger.debug("Canal creado con éxito")

        exchange_events = await channel.declare_exchange(name=exchange_events_name, type='topic', durable=True)

        exchange_commands = await channel.declare_exchange(name=exchange_commands_name, type='topic', durable=True)

        exchange_responses = await channel.declare_exchange(name=exchange_responses_name, type='topic', durable=True)
        rabbitmq_working = True
        set_rabbitmq_status(True)
        logger.info("rabbitmq_working : " + str(rabbitmq_working))
    except Exception as e:
        logger.error(f"Error durante la suscripción: {e}")
        raise  # Propaga el error para manejo en niveles superiores

async def on_message_payment_check(message):
    async with message.process():
        order = json.loads(message.body.decode())
        db = SessionLocal()
        balance, status = await crud.update_balance_by_id_client(db, order['id_client'], order['movement'])
        await db.close()
        data = {
            "id_order": order['id_order'],
            "status": status
        }
        message_body = json.dumps(data)
        logger.debug("el mensage que se envia es: " + message_body)
        routing_key = "payment.checked"
        await publish_response(message_body, routing_key)


async def subscribe_command_payment_check():
    # Create queue
    queue_name = "payment.check"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "payment.check"
    await queue.bind(exchange=exchange_commands_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_message_payment_check(message)



# Cancel

async def on_message_payment_check_order_cancel(message):
    async with message.process():
        payment = json.loads(message.body)
        db = SessionLocal()
        try:
            db_payment = await crud.create_recharge(db, payment)
            # Crear evento con payment de ID order correcto
            payment_status = True
        except Exception as exc:
            # Crear evento con payment de ID order incorrecto
            payment_status = False
        await db.close()
        data = {
            "order_id": payment['order_id'],
            "status": payment_status
        }
        message_body = json.dumps(data)
        routing_key = "payment.checked_cancel"
        await publish_response(message_body, routing_key)


async def subscribe_payment_check_order_cancel():
    # Create queue
    queue_name = "payment.check_cancel"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "payment.check_cancel"
    await queue.bind(exchange=exchange_commands_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_message_payment_check_order_cancel(message)



async def on_message_payment_revert_order_cancel(message):
    async with message.process():
        order_cancel = json.loads(message.body)
        db = SessionLocal()
        await crud.delete_recharge(db, order_cancel['id_client'])
        await db.close()
        data = {
            "order_id": order_cancel['order_id'],
            "id_client": order_cancel['id_client']
        }
        message_body = json.dumps(data)
        routing_key = "payment.reverted_cancel"
        await publish_response(message_body, routing_key)


async def subscribe_payment_revert_order_cancel():
    # Create queue
    queue_name = "payment.revert_cancel"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "payment.revert_cancel"
    await queue.bind(exchange=exchange_commands_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_message_payment_revert_order_cancel(message)


async def publish_event(message_body, routing_key):
    # Publish the message to the exchange
    await exchange_events.publish(
        aio_pika.Message(
            body=message_body.encode(),
            content_type="text/plain"
        ),
        routing_key=routing_key)


async def publish_command(message_body, routing_key):
    # Publish the message to the exchange
    await exchange_commands.publish(
        aio_pika.Message(
            body=message_body.encode(),
            content_type="text/plain"
        ),
        routing_key=routing_key)


async def publish_response(message_body, routing_key):
    # Publish the message to the exchange
    await exchange_responses.publish(
        aio_pika.Message(
            body=message_body.encode(),
            content_type="text/plain"
        ),
        routing_key=routing_key)

