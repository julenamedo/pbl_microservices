import asyncio
import aio_pika
import json
from app.sql.database import SessionLocal  # pylint: disable=import-outside-toplevel
from app.sql import crud, models
from app import dependencies
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
exchange_commands = None
exchange = None
exchange_commands_name = 'commands'
exchange_name = 'events'
exchange_responses_name = 'responses'
exchange_responses = None

async def subscribe_channel():
    """
    Conéctate a RabbitMQ utilizando SSL, declara los intercambios necesarios y configura el canal.
    """
    global channel, exchange_commands, exchange, exchange_commands_name, exchange_name, exchange_responses, exchange_responses_name

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

        # Declarar el intercambio específico
        exchange = await channel.declare_exchange(
            name=exchange_name,
            type='topic',
            durable=True
        )

        exchange_responses = await channel.declare_exchange(
            name=exchange_responses_name,
            type='topic',
            durable=True
        )
        logger.info(f"Intercambio '{exchange_name}' declarado con éxito")
        rabbitmq_working=True
        set_rabbitmq_status(True)
        logger.info("rabbitmq_working : "+str(rabbitmq_working))
    except Exception as e:
        logger.error(f"Error durante la suscripción: {e}")
        raise  # Propaga el error para manejo en niveles superiores


async def on_message_delivery_cancel(message):
    async with message.process():
        try:
            # Decodificar el mensaje
            order = json.loads(message.body.decode())

            # Usar una nueva sesión para cada operación
            async with SessionLocal() as db:
                async with db.begin():
                    # Obtener el delivery asociado al pedido
                    delivery = await crud.get_delivery_by_order(db, order['order_id'])
                    if not delivery:
                        logger.error("No se encontró la entrega para el pedido %s", order['order_id'])
                        return
                        return

                    # Actualizar el estado de la entrega
                    updated_delivery = await crud.update_delivery(db, delivery.order_id, models.Delivery.STATUS_CANCELED)
                    if not updated_delivery:
                        logger.error("Error al actualizar la entrega para el pedido %s", order['order_id'])
                        return

                    logger.info("Entrega actualizada: %s", updated_delivery)

            # Preparar y publicar el mensaje de respuesta
            data = {
                "id_order": order['order_id'],
                "id_client": order['id_client']
            }
            message_body = json.dumps(data)
            routing_key = "delivery.canceled"
            await publish_response(message_body, routing_key)

        except Exception as e:
            logger.error(f"Error al procesar el mensaje: {e}")


async def subscribe_delivery_cancel():
    # Create queue
    queue_name = "delivery.cancel"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "delivery.cancel"
    await queue.bind(exchange=exchange_commands_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_message_delivery_cancel(message)


async def on_produced_message(message):
    async with message.process():
        order = json.loads(message.body)
        db = SessionLocal()
        db_delivery = await crud.get_delivery_by_order_id(db, order['id_order'])
        if db_delivery.status != models.Delivery.STATUS_CANCELED:
            db_delivery = await crud.update_delivery(db, order['id_order'], models.Delivery.STATUS_DELIVERING)
            await db.close()
            asyncio.create_task(send_product(db_delivery))
        else:
            await db.close()

async def on_create_message(message):
    async with message.process():

        order = json.loads(message.body.decode())
        db = SessionLocal()
        address_check = await crud.check_address(db, order["id_client"])
        data = {
            "id_order": order["id_order"],
            "id_client": order['id_client'],
            "status": address_check
        }
        if address_check:
            status_delivery_address_check = models.Delivery.STATUS_CREATED
        else:
            status_delivery_address_check = models.Delivery.STATUS_CANCELED

        await crud.create_delivery(db, order["id_order"], order["id_client"], status_delivery_address_check)
        message = json.dumps(data)
        routing_key = "delivery.checked"
        logger.debug("Publishing message to delivery.checked: %s", message)
        await publish_response(message, routing_key)
        logger.debug("Message published to delivery.checked")

        await db.close()

async def subscribe_delivery_check():
    # Create queue
    queue_name = "delivery.check"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "delivery.check"
    await queue.bind(exchange=exchange_commands_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_create_message(message)

async def subscribe_produced():
    # Create queue
    queue_name = "orders.produced"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "orders.produced"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_produced_message(message)


async def send_product(delivery):
    logger.debug("HE ENTRADO")
    data = {
        "id_order": delivery.order_id,
        "id_client": delivery.id_client
    }
    message_body = json.dumps(data)

    # Publica el evento inicial con el estado "in process"
    routing_key = "orders.delivering"
    try:
        await publish_event(message_body, routing_key)
    except Exception as e:
        logger.error(f"Error al publicar el evento 'in process': {e}")
        return  # O maneja el error según sea necesario

    # Espera de 10 segundos
    await asyncio.sleep(10)

    # Actualiza el estado del delivery en la base de datos
    async with dependencies.get_db() as db:
        try:
            db_delivery = await crud.get_delivery(db, delivery.id)
            if db_delivery is None:
                logger.error(f"Delivery con ID {delivery.id} no encontrado")
                return

            db_delivery = await crud.update_delivery(db, delivery.order_id, models.Delivery.STATUS_DELIVERED)
            if db_delivery is None:
                logger.error(f"No se pudo actualizar el estado del delivery para ID {delivery.id}")
                return

            logger.debug(f"El delivery de la base de datos es: {db_delivery.id} con estado {db_delivery.status}")
        except Exception as e:
            logger.error(f"Error al obtener o actualizar el delivery: {e}")
            return

    routing_key = "orders.delivered"
    await publish_event(message_body, routing_key)

    # Cierra la sesión de la base de datos
    await db.close()


async def on_message_order_cancel_delivery_pending(message):
    async with message.process():
        order = json.loads(message.body)
        db = SessionLocal()
        delivery = await crud.get_delivery_by_order(db, order['id_order'])
        status = False
        if delivery.status_delivery == models.Delivery.STATUS_CREATED:
            await crud.update_delivery(db, order['id_order'], models.Delivery.STATUS_CANCELED)
            status = True
        await db.close()
        data = {
            "id_order": order['id_order'],
            "status": status
        }
        message_body = json.dumps(data)
        routing_key = "delivery.checked_cancel"
        await publish_response(message_body, routing_key)


async def subscribe_order_cancel_delivery_pending():
    # Create queue
    queue_name = "delivery.check_cancel"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "delivery.check_cancel"
    await queue.bind(exchange=exchange_commands_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_message_order_cancel_delivery_pending(message)


async def on_client_updated_message(message):
    async with message.process():
        client = json.loads(message.body)

        db = SessionLocal()
        info_client = models.Client(
            id_client=client['id_client'],
            address=client['address'],
            zip_code=client['zip_code']
        )
        await crud.update_address(db, info_client)
        await db.close()


async def subscribe_client_updated():
    # Create a queue
    queue_name = "client.updated"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "client.updated"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_client_updated_message(message)


async def on_client_created_message(message):
    async with message.process():
        client = json.loads(message.body)
        db = SessionLocal()
        info_client = models.Client(
            id_client=client['id_client'],
            address=client['address'],
            zip_code=client['zip_code']
        )
        await crud.update_address(db, info_client)
        await db.close()


async def subscribe_client_created():
    # Create a queue
    queue_name = "client.created"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "client.created"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_client_created_message(message)


async def publish_commands(message_body, routing_key):
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


async def publish_event(message_body, routing_key):
    # Publish the message to the exchange
    await exchange.publish(
        aio_pika.Message(
            body=message_body.encode(),
            content_type="text/plain"
        ),
        routing_key=routing_key)
