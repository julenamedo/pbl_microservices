# -*- coding: utf-8 -*-
"""Main file to start FastAPI application."""
import logging.config
import os
import aio_pika
import asyncio
from contextlib import asynccontextmanager

from .consulService.BLConsul import register_consul_service
from .consulService.BLConsul import unregister_consul_service

from fastapi import FastAPI
from app.routers import main_router, rabbitmq
from app.sql import models
from app.sql import database

from app.routers import rabbitmq_publish_logs
import global_variables
from global_variables.global_variables import update_system_resources_periodically, set_rabbitmq_status, get_rabbitmq_status

EXCHANGE_NAME = "exchange"

# Configure logging ################################################################################
print("Name: ", __name__)
logging.config.fileConfig(os.path.join(os.path.dirname(__file__), 'logging.ini'))
logger = logging.getLogger(__name__)

# OpenAPI Documentation ############################################################################
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")
logger.info("Running app version %s", APP_VERSION)
DESCRIPTION = """
Monolithic manufacturing order application.
"""

tag_metadata = [

    {
        "name": "Machine",
        "description": "Endpoints related to machines",
    },
    {
        "name": "Order",
        "description": "Endpoints to **CREATE**, **READ**, **UPDATE** or **DELETE** orders.",
    },
    {
        "name": "Piece",
        "description": "Endpoints **READ** piece information.",
    },

]

app = FastAPI(
    redoc_url=None,  # disable redoc documentation.
    title="FastAPI - Monolithic app",
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
    try:

        logger.info("antes del subscribe")

        async with database.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)


        await rabbitmq.subscribe_channel()
        await rabbitmq_publish_logs.subscribe_channel(aio_pika.ExchangeType.TOPIC, EXCHANGE_NAME)

        register_consul_service()

        logger.info("despues del subscribe")
        asyncio.create_task(rabbitmq.subscribe_create())
        asyncio.create_task(rabbitmq.subscribe_produced())
        asyncio.create_task(rabbitmq.subscribe_delivery_check())
        asyncio.create_task(rabbitmq.subscribe_delivery_cancel())


        message, routing_key = await rabbitmq_publish_logs.formato_log_message("debug", "inicializando Delivery correctamente")
        await rabbitmq_publish_logs.publish_log(message, routing_key)
        try:
            task = asyncio.create_task(update_system_resources_periodically(15))
        except Exception as e:
            logger.error(f"Error al monitorear recursos del sistema: {e}")
    except:
        message, routing_key = await rabbitmq_publish_logs.formato_log_message("error", "error inicializando Delivery")
        await rabbitmq_publish_logs.publish_log(message, routing_key)

@app.on_event("shutdown")
async def shutdown_event():
    unregister_consul_service()

if __name__ == "__main__":
    import uvicorn

    logger.debug("App run as script")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8002
    )
    logger.debug("App finished as script")
