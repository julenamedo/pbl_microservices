import asyncio
import aio_pika
import json
from app.sql.database import SessionLocal  # pylint: disable=import-outside-toplevel
from app.sql import crud
from app.sql import models, schemas
import logging
from app.routers import rabbitmq_publish_logs
from app import dependencies
import ssl
from global_variables.global_variables import update_system_resources_periodically, set_rabbitmq_status, get_rabbitmq_status

# Configura el logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración SSL
ssl_context = ssl.create_default_context(cafile="/keys/ca_cert.pem")
ssl_context.check_hostname = False  # Deshabilita la verificación del hostname
ssl_context.verify_mode = ssl.CERT_NONE  # No verifica el certificado del servidor

# Variables globales
channel = None
exchange_commands = None
exchange = None
exchange_commands_name = 'commands'
exchange_name = 'events'
exchange_responses_name = 'responses'
exchange_responses = None


async def subscribe_channel():
   
    global channel, exchange_commands, exchange, exchange_commands_name, exchange_name, exchange_responses_name, exchange_responses

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

        # Declarar el intercambio para "commands"
        exchange_commands = await channel.declare_exchange(
            name=exchange_commands_name,
            type='topic',
            durable=True
        )
        logger.info(f"Intercambio '{exchange_commands_name}' declarado con éxito")

        exchange_responses = await channel.declare_exchange(name=exchange_responses_name, type='topic', durable=True)

        # Declarar el intercambio específico
        exchange = await channel.declare_exchange(
            name=exchange_name,
            type='topic',
            durable=True
        )
        logger.info(f"Intercambio '{exchange_name}' declarado con éxito")
        rabbitmq_working=True
        set_rabbitmq_status(True)
        logger.info("rabbitmq_working : "+str(rabbitmq_working))
        # events
    except Exception as e:
        logger.error(f"Error durante la suscripción: {e}")
        raise  # Propaga el error para manejo en niveles superiores


async def on_piece_order(message):
    async with message.process():
        pieces_ordered = json.loads(message.body)
        db = SessionLocal()
        enough_pieces = True
        for _ in range(0, pieces_ordered['number_of_pieces_a']):
            db_pieces = await crud.get_order_pieces_by_type(db, None, "A")
            if db_pieces:
                db_piece = await crud.change_piece_order_id(db, db_pieces[0].id_piece, pieces_ordered['id_order'])
            else:
                piece = schemas.PieceBase(
                    piece_type="A",
                    status_piece=models.Piece.STATUS_QUEUED,
                    id_order=pieces_ordered['id_order'],
                    id_client=pieces_ordered['id_client']
                )
                await crud.create_piece(db, piece)
                enough_pieces = False
        for _ in range(0, pieces_ordered['number_of_pieces_b']):
            db_pieces = await crud.get_order_pieces_by_type(db, None, "B")
            if db_pieces:
                db_piece = await crud.change_piece_order_id(db, db_pieces[0].id_piece, pieces_ordered['id_order'])
            else:
                piece = schemas.PieceBase(
                    piece_type="B",
                    status_piece=models.Piece.STATUS_QUEUED,
                    id_order=pieces_ordered['id_order'],
                    id_client=pieces_ordered['id_client']
                )
                await crud.create_piece(db, piece)
                enough_pieces = False
        if enough_pieces:
            data = {
                "id_order": db_piece.id_order,
                "id_client": pieces_ordered['id_client']
            }
            message_body = json.dumps(data)
            routing_key = "order.produced"
            await publish(message_body, routing_key)
        await db.close()


async def subscribe_piece_order():
    # Create a queue
    queue_name = "warehouse.requested"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "warehouse.requested"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_piece_order(message)


async def on_piece_message(message):
    async with message.process():
        piece_recieve = json.loads(message.body)
        db = SessionLocal()
        db_piece = await crud.change_piece_status(db, piece_recieve['id_piece'], models.Piece.STATUS_PRODUCED)
        if (db_piece.id_order != None):
            db_pieces = await crud.get_order_pieces(db, db_piece.id_order)
            order_finished = True
            for piece in db_pieces:
                if piece.status_piece == models.Piece.STATUS_QUEUED:
                    order_finished = False
                    break
            if order_finished:
                data = {
                    "id_order": db_piece.id_order,
                    "id_client": db_piece.id_client
                }
                message_body = json.dumps(data)
                routing_key = "order.produced"
                await publish(message_body, routing_key)
        await db.close()


async def subscribe_pieces():
    # Create a queue
    queue_name = "piece.produced"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "piece.produced"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_piece_message(message)


async def subscribe_delivery_cancel():
    # Create queue
    queue_name = "warehouse.cancel_check"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "warehouse.cancel_check"
    await queue.bind(exchange=exchange_responses_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_message_delivery_cancel(message)


async def on_delivering(message):
    async with message.process():
        delivery = json.loads(message.body)
        db = SessionLocal()
        db_pieces = await crud.get_order_pieces(db, delivery['id_order'])
        await db.close()
        for piece in db_pieces:
            db = SessionLocal()
            await crud.change_piece_status(db, piece.id_piece, models.Piece.STATUS_SHIPPED)
            await db.close()


async def subscribe_delivering():
    queue_name = "order.delivering"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "order.delivering"

    await queue.bind(exchange=exchange_responses_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_delivering(message)


async def on_message_delivery_cancel(message):
    async with message.process():
        order_canceled = json.loads(message.body)
        status_canceled = True
        try:
            db = SessionLocal()
            db_pieces = await crud.get_order_pieces(db, order_canceled['id_order'])
            await db.close()
            for piece in db_pieces:
                db = SessionLocal()
                db_piece = await crud.change_piece_order_id(db, piece.id_piece, None)
                await db.close()
        except Exception as e:
            status_canceled = False
        data = {
            "id_order": order_canceled['id_order'],
            "id_client": order_canceled['id_client'],
            "status": status_canceled
        }
        message_body = json.dumps(data)
        routing_key = "warehouse.order_canceled"
        await publish_response(message_body, routing_key)


async def publish(message_body, routing_key):
    # Publish the message to the exchange
    await exchange.publish(
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


