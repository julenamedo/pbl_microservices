import aio_pika
import logging
import json

from app.sql import crud, models
import ssl
from global_variables.global_variables import update_system_resources_periodically, set_rabbitmq_status, get_rabbitmq_status
from datetime import datetime
from app.sql.database import write_api, INFLUXDB_BUCKET, INFLUXDB_ORG
from influxdb_client import Point
import traceback


logger = logging.getLogger(__name__)



# Configura el logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ssl_context = ssl.create_default_context(cafile="/keys/ca_cert.pem")
ssl_context.check_hostname = False  # Deshabilita la verificación del hostname
ssl_context.verify_mode = ssl.CERT_NONE  # No verifica el certificado del servidor

# Variables globales
channel = None
exchange_commands = None
exchange = None
exchange_responses = None
exchange_logs = None
exchange_commands_name = 'commands'
exchange_name = 'events'
exchange_responses_name = 'responses'
exchange_logs_name = 'responses'

async def subscribe_channel():

    global channel, exchange_logs_name, exchange_logs, exchange, exchange_name, exchange_commands, exchange_responses_name, exchange_responses, exchange_commands_name

    try:
        # Establece la conexión robusta con RabbitMQ utilizando TLS
        connection = await aio_pika.connect_robust(
            host='rabbitmq',
            port=5671,  # Puerto seguro TLS
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
        logger.info(f"Intercambio '{exchange_name}' declarado con éxito")

        exchange_responses = await channel.declare_exchange(
            name=exchange_responses_name,
            type='topic',
            durable=True
        )
        logger.info(f"Intercambio '{exchange_responses_name}' declarado con éxito")

        exchange_logs = await channel.declare_exchange(
            name=exchange_logs_name,
            type='topic',
            durable=True
        )
        logger.info(f"Intercambio '{exchange_logs_name}' declarado con éxito")

        rabbitmq_working = True
        set_rabbitmq_status(True)
        logger.info("rabbitmq_working : " + str(rabbitmq_working))

    except Exception as e:
        logger.error(f"Error durante la suscripción ")
        raise  # Propaga el error para manejo en niveles superiores


async def on_log_message(message):
    async with message.process():
        try:
            # Log básico al recibir un mensaje
            logger.info(f" [x] Received message from {exchange_name}: {message.body.decode()}")
            print(f" [x] Received message from {exchange_name}: {message.body.decode()}")

            # Extraer datos del mensaje
            routing_key = message.routing_key
            data = message.body.decode()
            log_level = "INFO"  # Puedes ajustar dinámicamente el nivel de log según el caso

            # Crear un punto de datos para InfluxDB
            point = Point("logs") \
                .tag("exchange", exchange_name) \
                .tag("routing_key", routing_key) \
                .tag("log_level", log_level) \
                .field("message", data) \
                .time(datetime.utcnow().isoformat())

            # Escribir en InfluxDB
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)

            print(f"Log saved to InfluxDB: {data}")

        except Exception as e:
            # Capturar excepciones y registrar como ERROR
            exception_message = traceback.format_exception(None, e, e.__traceback__)
            logger.error(f" [!] Error processing message: {exception_message}")
            print(f" [!] Error processing message: {exception_message}")

            # Crear un log para la excepción
            point = Point("logs") \
                .tag("exchange", exchange_name) \
                .tag("routing_key", "error") \
                .tag("log_level", "ERROR") \
                .field("message", "Error processing message") \
                .field("exception", "\n".join(exception_message)) \
                .time(datetime.utcnow().isoformat())

            # Escribir el error en InfluxDB
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)

            print("Error log saved to InfluxDB")


async def subscribe_events_logs():
    queue_name = "logs_events"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "#"
    await queue.bind(exchange=exchange_name, routing_key=routing_key)

    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_log_message(message)

async def on_command_log_message(message):
    async with message.process():
        try:
            # Extraer datos del mensaje
            routing_key = message.routing_key
            data = message.body.decode()
            log_level = "INFO"  # Establece un nivel de log, puedes ajustarlo según el caso

            # Crear un punto de datos para InfluxDB
            point = Point("logs") \
                .tag("exchange", exchange_commands_name) \
                .tag("routing_key", routing_key) \
                .tag("log_level", log_level) \
                .field("message", data) \
                .time(datetime.utcnow().isoformat())

            # Escribir en InfluxDB
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)

            print(f"Command log saved to InfluxDB: {data}")

        except Exception as e:
            # Manejo de excepciones y registro de error
            exception_message = traceback.format_exception(None, e, e.__traceback__)
            logger.error(f" [!] Error processing command log message: {exception_message}")
            print(f" [!] Error processing command log message: {exception_message}")

            # Crear un log para la excepción
            point = Point("logs") \
                .tag("exchange", exchange_commands_name) \
                .tag("routing_key", "error") \
                .tag("log_level", "ERROR") \
                .field("message", "Error processing command log message") \
                .field("exception", "\n".join(exception_message)) \
                .time(datetime.utcnow().isoformat())

            # Escribir el error en InfluxDB
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)

            print("Error log saved to InfluxDB")


async def subscribe_commands_logs():
    # Create a queue
    queue_name = "commands_logs"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "#"
    await queue.bind(exchange=exchange_commands, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_command_log_message(message)


async def on_response_log_message(message):
    async with message.process():
        try:

            # Extraer información del mensaje
            routing_key = message.routing_key
            data = message.body.decode()
            log_level = "INFO"  # Nivel de log predeterminado

            # Crear un punto para InfluxDB
            point = Point("logs") \
                .tag("exchange", exchange_responses_name) \
                .tag("routing_key", routing_key) \
                .tag("log_level", log_level) \
                .field("message", data) \
                .time(datetime.utcnow().isoformat())

            # Escribir el log en InfluxDB
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)

            print(f"Response log saved to InfluxDB: {data}")

        except Exception as e:
            # Manejo de excepciones
            exception_message = traceback.format_exception(None, e, e.__traceback__)
            logger.error(f" [!] Error processing response log message: {exception_message}")
            print(f" [!] Error processing response log message: {exception_message}")

            # Crear un punto de log para la excepción
            point = Point("logs") \
                .tag("exchange", exchange_responses_name) \
                .tag("routing_key", "error") \
                .tag("log_level", "ERROR") \
                .field("message", "Error processing response log message") \
                .field("exception", "\n".join(exception_message)) \
                .time(datetime.utcnow().isoformat())

            # Escribir el log de error en InfluxDB
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)

            print("Error log saved to InfluxDB")


async def subscribe_responses_logs():
    # Create a queue
    queue_name = "responses_logs"
    queue = await channel.declare_queue(name=queue_name, exclusive=True)
    # Bind the queue to the exchange
    routing_key = "#"
    await queue.bind(exchange=exchange_responses, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_response_log_message(message)


async def on_log_log_message(message):
    async with message.process():
        try:
            # Extraer información del mensaje
            routing_key = message.routing_key
            data = message.body.decode()
            log_level = "INFO"  # Nivel de log predeterminado

            # Crear un punto para InfluxDB
            point = Point("logs") \
                .tag("exchange", exchange_logs_name) \
                .tag("routing_key", routing_key) \
                .tag("log_level", log_level) \
                .field("message", data) \
                .time(datetime.utcnow().isoformat())

            # Escribir el log en InfluxDB
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)

            print(f"Response log saved to InfluxDB: {data}")

        except Exception as e:
            # Manejo de excepciones
            exception_message = traceback.format_exception(None, e, e.__traceback__)
            logger.error(f" [!] Error processing response log message: {exception_message}")
            print(f" [!] Error processing response log message: {exception_message}")

            # Crear un punto de log para la excepción
            point = Point("logs") \
                .tag("exchange", exchange_logs_name) \
                .tag("routing_key", "error") \
                .tag("log_level", "ERROR") \
                .field("message", "Error processing response log message") \
                .field("exception", "\n".join(exception_message)) \
                .time(datetime.utcnow().isoformat())

            # Escribir el log de error en InfluxDB
            write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)

            print("Error log saved to InfluxDB")


async def subscribe_logs_logs():
    # Create a queue
    queue_name = "logs_logs"
    queue = await channel.declare_queue(name=queue_name, exclusive=False)
    # Bind the queue to the exchange
    routing_key = "#"
    await queue.bind(exchange=exchange_logs, routing_key=routing_key)
    # Set up a message consumer
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            await on_log_log_message(message)
