# -*- coding: utf-8 -*-
"""Main file to start FastAPI application."""
import logging.config
import os
import asyncio
import time

import aio_pika
from contextlib import asynccontextmanager
# from loki_logger_handler.loki_logger_handler import LokiLoggerHandler
# from loki_logger_handler.formatters.loguru_formatter import LoguruFormatter
from loguru import logger
from .consulService.BLConsul import register_consul_service, unregister_consul_service

from fastapi import FastAPI
import requests
from app.routers import main_router, rabbitmq, rabbitmq_publish_logs
from app.sql import models
from app.sql import database
import global_variables
from global_variables.global_variables import update_system_resources_periodically, set_rabbitmq_status, get_rabbitmq_status

# Configure logging ################################################################################
print("Name: ", __name__)
logging.config.fileConfig(os.path.join(os.path.dirname(__file__), 'logging.ini'))
# logger = logging.getLogger(__name__)
# Configura Loguru para Loki


class LokiLoggerHandler(logging.Handler):
    def __init__(self, url, labels):
        super().__init__()
        self.url = url
        self.labels = labels

    def emit(self, message):
        # Extract the structured record from Loguru's message object
        log_record = message.record
        log_message = log_record["message"]

        # Prepare the Loki payload
        payload = {
            "streams": [
                {
                    "stream": self.labels,
                    "values": [
                        [str(int(time.time() * 1e9)), log_message]  # Current timestamp in nanoseconds
                    ],
                }
            ]
        }

        # Send the payload to Loki
        try:
            response = requests.post(self.url, json=payload)
            if response.status_code != 204:
                print(f"Failed to send log to Loki: {response.status_code}, {response.text}")
        except Exception as e:
            print(f"Error sending log to Loki: {e}")


custom_handler = LokiLoggerHandler(
    url="https://loki:3100/loki/api/v1/push",  # Dirección de Loki
    labels={"job": "log-service", "environment": "development"},
)
# Añade el handler de Loki a Loguru
logger.add(
    custom_handler.emit,  # Pass the emit method of the handler as a sink
    level="DEBUG",
    serialize=True
)


logger.info("This is a test log for Loki")

print(f"Loki Logger Labels: {custom_handler.labels}")


# OpenAPI Documentation ############################################################################
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")
logger.info("Running app version %s", APP_VERSION)
DESCRIPTION = """
Monolithic log application.
"""


tag_metadata = [

    {
        "name": "Log",
        "description": "Endpoints related to logs",
    },

]

app = FastAPI(
    redoc_url=None,  # disable redoc documentation.
    title="FastAPI - Log app",
    description=DESCRIPTION,
    version=APP_VERSION,
    servers=[
        {"url": "/", "description": "Development"}
    ],
    license_info={
        "name": "MIT License",
        "url": "https://choosealicense.com/licenses/mit/"
    },
    openapi_tags=tag_metadata

)

app.include_router(main_router.router)

@app.on_event("startup")
async def startup_event():
    """Configuration to be executed when FastAPI server starts."""
    try:
        logger.info("Creating database tables")
        # async with database.engine.begin() as conn:
        #     await conn.run_sync(models.Base.metadata.create_all)
        # await rabbitmq.subscribe_channel()
        # Suscripción a canales y tareas de RabbitMQ

        # Initialize InfluxDB
        logger.info("Connecting to InfluxDB...")
        try:
            influx_health = database.influxdb_client.health()
            logger.info(f"InfluxDB Health: {influx_health}")
        except Exception as e:
            logger.error(f"Failed to connect to InfluxDB: {e}")
            raise

        await rabbitmq.subscribe_channel()
        await rabbitmq_publish_logs.subscribe_channel()
        register_consul_service()

        asyncio.create_task(rabbitmq.subscribe_events_logs())
        asyncio.create_task(rabbitmq.subscribe_commands_logs())
        asyncio.create_task(rabbitmq.subscribe_responses_logs())
        asyncio.create_task(rabbitmq.subscribe_logs_logs())

        # Monitorización de recursos del sistema
        try:
            task = asyncio.create_task(update_system_resources_periodically(15))
        except Exception as e:
            logger.error(f"Error al monitorear recursos del sistema: {e}")

        logger.info("Despues de create_task")
    except Exception as main_exception:
        logger.error(f"Error during startup configuration: {main_exception}")

@app.on_event("shutdown")
async def shutdown_event():
    unregister_consul_service()

# Main #############################################################################################
# If application is run as script, execute uvicorn on port 8000
if __name__ == "__main__":
    import uvicorn

    logger.debug("App run as script")
    print("Starting uvicorn...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8005,
        log_config='logging.ini'
    )
    logger.debug("App finished as script")