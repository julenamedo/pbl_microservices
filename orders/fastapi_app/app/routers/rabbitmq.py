import asyncio
import aio_pika
import json
from app.sql.database import SessionLocal  # pylint: disable=import-outside-toplevel
from app.sql import crud
from app.sql import models, schemas
import logging
from os import environ
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
            host=environ.get("RABBITMQ_HOST"),
            port=int(environ.get("RABBITMQ_PORT_SERVICE")),  # Puerto seguro SSL
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

        exchange_responses = await channel.declare_exchange(
            name=exchange_responses_name,
            type='topic',
            durable=True
        )
        logger.info(f"Intercambio '{exchange_responses_name}' declarado con éxito")

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


async def on_delivery_checked_order_cancel_message(message):
    async with message.process():
        delivery = json.loads(message.body)
        db = SessionLocal()
        db_saga = SessionLocal()
        db_catalog = SessionLocal()
        # meter un parametro en el mensaje desde delivery que sea status (T/F)
        if delivery['status']:
            db_order = await crud.update_order_status(db, delivery['order_id'], models.Order.STATUS_ORDER_CANCEL_PAYMENT_PENDING)
            await crud.create_sagas_history(db_saga, delivery['order_id'], db_order.status)
            db_catalog_piece_a = await crud.get_piece_from_catalog_by_piece_type(db_catalog, "A")
            db_catalog_piece_b = await crud.get_piece_from_catalog_by_piece_type(db_catalog, "B")
            data = {
                "order_id": db_order.id,
                "id_client": db_order.id_client,
                "movement": (db_order.number_of_pieces_a * db_catalog_piece_a.price + db_order.number_of_pieces_b * db_catalog_piece_b.price)
            }
            message_body = json.dumps(data)
            routing_key = "payment.check_cancel"
            await publish_command(message_body, routing_key)
        else:
            db_order = await crud.update_order_status(db, delivery['order_id'], models.Order.STATUS_QUEUED)
            await crud.create_sagas_history(db_saga, delivery['order_id'], db_order.status)
        await db.close()
        await db_saga.close()
        await db_catalog.close()


async def subscribe_delivery_checked_order_cancel():
    # Create a queue
    # Viene de delivery
    queue_name = "delivery.checked_cancel"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "delivery.checked_cancel"
    await queue.bind(exchange=exchange_responses_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_delivery_checked_order_cancel_message(message)


async def on_order_delivered_message(message):
    async with message.process():
        order = json.loads(message.body.decode())
        db = SessionLocal()
        db_order = await crud.update_order_status(db, order['id_order'], models.Order.STATUS_DELIVERED)
        # await rabbitmq_publish_logs.publish_log("order " + order['id_order'] + "delivered", "logs.info.order")
        await db.close()


async def subscribe_order_finished():
    # Create a queue
    queue_name = "orders.delivered"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "orders.delivered"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_order_delivered_message(message)



async def on_payment_checked_order_cancel_message(message):
    async with message.process():
        payment = json.loads(message.body)
        db = SessionLocal()
        db_saga = SessionLocal()
        if payment['status']:
            db_order = await crud.update_order_status(db, payment['order_id'], models.Order.STATUS_ORDER_CANCEL_WAREHOUSE_PENDING)
            await crud.create_sagas_history(db_saga, payment['order_id'], db_order.status_)
            data = {
                "order_id": db_order.id,
                "id_client": db_order.id_client
            }
            message_body = json.dumps(data)
            routing_key = "warehouse.check_cancel"
            await publish_command(message_body, routing_key)
        else:
            db_order = await crud.update_order_status(db, payment['order_id'], models.Order.STATUS_ORDER_CANCEL_DELIVERY_REDELIVERING)
            await crud.create_sagas_history(db_saga, payment['order_id'], db_order.status)
            data = {
                "order_id": db_order.id
            }
            message_body = json.dumps(data)
            routing_key = "delivery.revert_cancel"
            await publish_command(message_body, routing_key)
        await db.close()
        await db_saga.close()

async def subscribe_payment_checked_order_cancel():
    # Create a queue
    queue_name = "payment.checked_cancel"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "payment.checked_cancel"
    await queue.bind(exchange=exchange_responses_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_payment_checked_order_cancel_message(message)


async def on_delivery_reverted_order_cancel_message(message):
    async with message.process():
        delivery = json.loads(message.body)
        db = SessionLocal()
        db_saga = SessionLocal()
        db_order = await crud.update_order_status(db, delivery['order_id'], models.Order.STATUS_QUEUED)
        await crud.create_sagas_history(db_saga, delivery['order_id'], db_order.status)
        await db.close()
        await db_saga.close()


async def subscribe_delivery_reverted_order_cancel():
    # Create a queue
    queue_name = "delivery.reverted_cancel"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "delivery.reverted_cancel"
    await queue.bind(exchange=exchange_responses_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_delivery_reverted_order_cancel_message(message)



async def on_warehouse_checked_order_cancel_message(message):
    async with message.process():
        warehouse = json.loads(message.body)
        db = SessionLocal()
        db_saga = SessionLocal()
        if warehouse['status']:
            db_order = await crud.update_order_status(db, warehouse['order_id'], models.Order.STATUS_CANCELED)
            await crud.create_sagas_history(db_saga, warehouse['order_id'], db_order.status)
        else:
            db_order = await crud.update_order_status(db, warehouse['order_id'], models.Order.STATUS_ORDER_CANCEL_PAYMENT_RECHARGING)
            await crud.create_sagas_history(db_saga, warehouse['order_id'], db_order.status)
            data = {
                "order_id": db_order.id,
                "id_client": db_order.id_client
            }
            message_body = json.dumps(data)
            routing_key = "payment.revert_cancel"
            await publish_command(message_body, routing_key)
        await db.close()
        await db_saga.close()


async def subscribe_warehouse_checked_order_cancel():
    # Create a queue
    queue_name = "warehouse.checked_cancel"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "warehouse.checked_cancel"
    await queue.bind(exchange=exchange_responses_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_warehouse_checked_order_cancel_message(message)



async def on_payment_reverted_order_cancel_message(message):
    async with message.process():
        payment = json.loads(message.body)
        db = SessionLocal()
        db_saga = SessionLocal()
        db_order = await crud.update_order_status(db, payment['order_id'], models.Order.STATUS_ORDER_CANCEL_DELIVERY_REDELIVERING)
        await crud.create_sagas_history(db_saga, payment['order_id'], db_order.status)
        data = {
            "order_id": db_order.id
        }
        message_body = json.dumps(data)
        routing_key = "delivery.revert_cancel"
        await publish_command(message_body, routing_key)
        await db.close()
        await db_saga.close()


async def subscribe_payment_reverted_order_cancel():
    # Create a queue
    queue_name = "payment.reverted_cancel"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "payment.reverted_cancel"
    await queue.bind(exchange=exchange_responses_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_payment_reverted_order_cancel_message(message)




async def on_delivering_message(message):
    async with message.process():
        delivery = json.loads(message.body)
        db = SessionLocal()
        db_order = await crud.update_order_status(db, delivery['id_order'], models.Order.STATUS_DELIVERING)
        await db.close()


async def subscribe_delivering():
    # Create a queue
    queue_name = "orders.delivering"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "orders.delivering"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_delivering_message(message)


async def on_produced_message(message):
    async with message.process():
        order = json.loads(message.body)
        db = SessionLocal()
        db_order = await crud.update_order_status(db, order['id_order'], models.Order.STATUS_PRODUCED)
        await db.close()


async def subscribe_produced():
    # Create queue
    # Viene de warehouse
    queue_name = "orders.produced_orders"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "orders.produced"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_produced_message(message)


async def on_payment_checked_message(message):
    async with message.process():
        payment = json.loads(message.body)
        try:
            async with SessionLocal() as db, SessionLocal() as db_saga:
                if payment['status']:
                    db_order = await crud.update_order_status(db, payment['id_order'], models.Order.STATUS_QUEUED)
                    if await crud.check_sagas_payment_status(db, payment['id_order']) == 1:
                        await crud.create_sagas_history(db_saga, payment['id_order'], models.Order.STATUS_QUEUED)
                    data = {
                        "id_order": db_order.id,
                        "number_of_pieces_a": db_order.number_of_pieces_a,
                        "number_of_pieces_b": db_order.number_of_pieces_b,
                        "id_client": db_order.id_client
                    }
                    message_body = json.dumps(data)
                    routing_key = "warehouse.requested"
                    await publish(message_body, routing_key)

                    # Crear las piezas de la orden (lo voy a poner en el rabbitmq de warehouse)
                    # for _ in range(db_order.number_of_pieces):
                    #     db_piece = await crud.add_piece_to_order(db, db_order)
                    #     data = {
                    #         "piece_id": db_piece.id,
                    #         "order_id": db_order.id
                    #     }
                    #     logger.info("pieza " + str(db_piece.id) + " creada para order " + str(db_order.id))
                    #     message_body = json.dumps(data)
                    #     routing_key = "events.piece.created"
                    #     await publish(message_body, routing_key)
                    #     await rabbitmq_publish_logs.publish_log("Petición de hacer pieza enviada", "logs.info.order")

                else:
                    db_order = await crud.update_order_status(db, payment['id_order'], models.Order.STATUS_DELIVERY_CANCELING)
                    if await crud.check_sagas_payment_status(db, payment['id_order']) == 1:
                        await crud.create_sagas_history(db_saga, payment['id_order'], models.Order.STATUS_DELIVERY_CANCELING)
                    data = {
                        "order_id": db_order.id,
                        "id_client": db_order.id_client
                    }
                    message_body = json.dumps(data)
                    routing_key = "delivery.cancel"
                    await publish_command(message_body, routing_key)
                await db.close()
                await db_saga.close()
        except Exception as e:
            logger.error(f"Error al procesar el pago para la orden {payment['id_order']}: {e}")
            raise


async def subscribe_delivery_cancel():
    # Create queue
    queue_name = "delivery.canceled"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
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
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
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


async def on_delivery_checked_message(message):
    """Manejador del mensaje de 'delivery checked'."""
    async with message.process():
        try:
            logger.debug("he recibido mensaje de delivery.checked")
            db = SessionLocal()
            db_saga = SessionLocal()
            db_catalog = SessionLocal()

            # Decodificación del mensaje
            try:
                delivery = json.loads(message.body)
                logger.debug(f"Mensaje decodificado correctamente: {delivery}")
            except json.JSONDecodeError as e:
                logger.error(f"Error al decodificar el mensaje JSON: {e}")
                return

            # Validación del mensaje
            required_keys = ['status', 'id_order', 'id_client']
            if not all(key in delivery for key in required_keys):
                logger.error(f"Mensaje incompleto recibido: {delivery}")
                return

            # Lógica basada en el estado del delivery
            if delivery['status']:
                logger.debug("Procesando estado 'true'")
                async with db:
                    logger.debug("Actualizando estado de la orden a PAYMENT_PENDING")
                    db_order = await crud.update_order_status(db, delivery['id_order'], models.Order.STATUS_PAYMENT_PENDING)

                    if not db_order:
                        logger.error(f"Orden con ID {delivery['id_order']} no encontrada.")
                        return

                    async with db_saga:
                        if await crud.check_sagas_payment_status(db, delivery['id_order']) == 0:
                            await crud.create_sagas_history(db_saga, delivery['id_order'], models.Order.STATUS_PAYMENT_PENDING)

                    logger.debug("Obteniendo piezas del catálogo")
                    db_catalog_piece_a = await crud.get_piece_from_catalog_by_piece_type(db_catalog, "A")
                    db_catalog_piece_b = await crud.get_piece_from_catalog_by_piece_type(db_catalog, "B")

                    if not db_catalog_piece_a or not db_catalog_piece_b:
                        logger.error("No se encontraron las piezas del catálogo")
                        return

                    data = {
                        "id_order": db_order.id,
                        "id_client": db_order.id_client,
                        "movement": -(db_order.number_of_pieces_a * db_catalog_piece_a.price + db_order.number_of_pieces_b * db_catalog_piece_b.price)
                    }
                    message_body = json.dumps(data)
                    routing_key = "payment.check"
                    logger.debug("Publicando mensaje en la cola de pagos")
                    await publish_command(message_body, routing_key)
            else:
                logger.debug("Procesando estado 'false'")
                async with db:
                    db_order = await crud.update_order_status(db, delivery['id_order'], models.Order.STATUS_CANCELED)

                    if not db_order:
                        logger.error(f"Orden con ID {delivery['id_order']} no encontrada para cancelar.")
                        return

                    async with db_saga:
                        await crud.create_sagas_history(db_saga, delivery['id_order'], models.Order.STATUS_CANCELED)
        except Exception as e:
            logger.error(f"Error al procesar el mensaje: {e}")
        finally:
            await db.close()
            await db_saga.close()
            await db_catalog.close()
            logger.debug("Conexiones a la base de datos cerradas")



async def subscribe_delivery_checked():
    # Create a queue
    queue_name = "delivery.checked"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "delivery.checked"

    await queue.bind(exchange=exchange_responses_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_delivery_checked_message(message)


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


async def publish_responses(message_body, routing_key):
    # Publish the message to the exchange
    await exchange_responses.publish(
        aio_pika.Message(
            body=message_body.encode(),
            content_type="text/plain"
        ),
        routing_key=routing_key)

