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
exchange_name = 'exchange'
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


async def on_piece_message(message):
    async with message.process():
        piece_recieve = json.loads(message.body)
        db = SessionLocal()
        db_order = await crud.get_order(db, piece_recieve['id_order'])
        logger.debug("la order recibida ess: " + db_order)
        db_piece = await crud.update_piece_status(db, piece_recieve['id_piece'], models.Piece.STATUS_MANUFACTURED)
        db_pieces = await crud.get_piece_list_by_order(db, piece_recieve['id_order'])
        order_finished = True
        logger.info("esta llegando la pieza terminada " + str(piece_recieve['id_piece']) + " a order " + str(db_order.id))
        for piece in db_pieces:
            if piece.status == models.Piece.STATUS_QUEUED:
                order_finished = False
                break
        if order_finished:
            logger.debug("el estado de la order es finished FINISH")
            db_order = await crud.update_order_status(db, piece_recieve['id_order'], models.Order.STATUS_FINISHED)
            data = {
                "id_order": piece_recieve['id_order']
            }
            message_body = json.dumps(data)
            routing_key = "events.order.produced"
            await publish(message_body, routing_key)
            await rabbitmq_publish_logs.publish_log("Todas las piezas del order producidas", "logs.info.order")
        await db.close()

async def on_order_delivered_message(message):
    async with message.process():
        order = json.loads(message.body.decode())
        db = SessionLocal()
        db_order = await crud.update_order_status(db, order['id_order'], models.Order.STATUS_DELIVERED)
        await rabbitmq_publish_logs.publish_log("order " + order['id_order'] + "delivered", "logs.info.order")
        await db.close()

async def subscribe_pieces():
    # Create a queue
    queue_name = "events.piece.produced"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "events.piece.produced"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_piece_message(message)

async def subscribe_order_finished():
    # Create a queue
    queue_name = "events.order.delivered"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "events.order.delivered"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_order_delivered_message(message)


async def on_payment_checked_message(message):
    async with message.process():
        payment = json.loads(message.body)
        try:
            async with SessionLocal() as db, SessionLocal() as db_saga:
                if payment['status']:
                    db_order = await crud.update_order_status(db, payment['id_order'], models.Order.STATUS_PAYMENT_DONE)
                    if await crud.check_sagas_payment_status(db, payment['id_order']) == 1:
                        await crud.create_sagas_history(db_saga, payment['id_order'], models.Order.STATUS_PAYMENT_DONE)
                    data = {
                        "id_order": db_order.id,
                        "user_id": db_order.id_client
                    }
                    message_body = json.dumps(data)
                    routing_key = "events.order.created"
                    await publish(message_body, routing_key)
                    await rabbitmq_publish_logs.publish_log(
                        "El order ha sido pagado por el cliente " + str(db_order.id_client), "logs.info.order")

                    # Crear las piezas de la orden
                    for _ in range(db_order.number_of_pieces):
                        db_piece = await crud.add_piece_to_order(db, db_order)
                        data = {
                            "piece_id": db_piece.id,
                            "order_id": db_order.id
                        }
                        logger.info("pieza " + str(db_piece.id) + " creada para order " + str(db_order.id))
                        message_body = json.dumps(data)
                        routing_key = "events.piece.created"
                        await publish(message_body, routing_key)
                        await rabbitmq_publish_logs.publish_log("Petición de hacer pieza enviada", "logs.info.order")

                    # pydantic_order = schemas.Order.from_orm(db_order)
                    # order_json = pydantic_order.dict()
                else:
                    db_order = await crud.update_order_status(db, payment['id_order'], models.Order.STATUS_PAYMENT_CANCELED)
                    if await crud.check_sagas_payment_status(db, payment['id_order']) == 1:
                        await crud.create_sagas_history(db_saga, payment['id_order'], models.Order.STATUS_PAYMENT_CANCELED)
                    data = {
                        "order_id": db_order.id
                    }
                    message_body = json.dumps(data)
                    routing_key = "delivery.cancel"
                    await publish_command(message_body, routing_key)
                    await rabbitmq_publish_logs.publish_log(
                        "El balance no es suficiente para el cliente ", "logs.error.order")
                await db.close()
                await db_saga.close()
        except Exception as e:
            logger.error(f"Error al procesar el pago para la orden {payment['id_order']}: {e}")
            raise


async def subscribe_delivery_cancel():
    # Create queue
    queue_name = "delivery.canceled"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "delivery.canceled"
    await queue.bind(exchange=exchange_responses_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_message_delivery_cancel(message)


async def subscribe_command_payment_checked():
    # Create a queue
    queue_name = "payment.checked"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "payment.checked"
    await queue.bind(exchange=exchange_responses_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            try:
                await on_payment_checked_message(message)
            except Exception as e:
                logger.error(f"Error processing message: {e}")


async def subscribe_payment_checked():
    # Create a queue
    queue_name = "events.order.checked"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "events.order.checked"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    asyncio.sleep(1)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            try:
                await on_payment_checked_message(message)
            except Exception as e:
                logger.error(f"Error processing message: {e}")


async def on_delivery_checked_message(message):
    """Manejador del mensaje de 'delivery checked'."""
    async with message.process():

        try:
            db = SessionLocal()
            db_saga = SessionLocal()
            # Carga el mensaje recibido
            delivery = json.loads(message.body.decode())


            # Maneja la lógica basada en el estado del delivery
            if delivery['status']:
                logger.debug("el estado de el delivery ESS:")
                async with db:
                    db_order = await crud.update_order_status(db, delivery['id_order'],
                                                              "PaymentPending")

                    # Verifica si la orden existe antes de continuar
                    if not db_order:
                        logger.error(f"Orden con ID {delivery['id_order']} no encontrada.")
                        return

                    async with db_saga:
                        if await crud.check_sagas_payment_status(db, delivery['id_order']) == 0:
                            await crud.create_sagas_history(db_saga, delivery['id_order'],
                                                            "PaymentPending")

                    # Construye el mensaje para la cola de pagos
                    data = {
                        "id_order": db_order.id,  # Asegúrate de que el atributo sea correcto
                        "id_client": db_order.id_client,
                        "movement": -(db_order.number_of_pieces)
                    }
                    message_body = json.dumps(data)
                    routing_key = "payment.check"

                    # Publica el comando
                    await publish_command(message_body, routing_key)

            else:
                async with db:
                    db_order = await crud.update_order_status(db, delivery['id_order'], "Canceled")

                    # Verifica si la orden existe antes de continuar
                    if not db_order:
                        logger.error(f"Orden con ID {delivery['id_order']} no encontrada para cancelar.")
                        return

                    async with db_saga:
                        await crud.create_sagas_history(db_saga, delivery['id_order'], "Canceled")

        except Exception as e:
            logger.error(f"Error al procesar el mensaje: {e}")


async def subscribe_delivery_checked():
    # Create a queue
    queue_name = "delivery.checked"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "delivery.checked"

    await queue.bind(exchange=exchange_responses_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_delivery_checked_message(message)


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


async def on_message_delivery_cancel(message):
    async with message.process():
        delivery = json.loads(message.body.decode())
        db = SessionLocal()
        db_saga = SessionLocal()
        db_order = await crud.update_order_status(db, delivery['id_order'], models.Order.STATUS_CANCELED)
        if await crud.check_sagas_payment_status(db, delivery['id_order']) == 1:
            await crud.create_sagas_history(db_saga, delivery['id_order'], models.Order.STATUS_CANCELED)
        await db.close()
        await db_saga.close()
