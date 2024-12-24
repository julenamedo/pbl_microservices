# -*- coding: utf-8 -*-
"""Main file to start FastAPI application."""
import logging.config
import os
import json
import asyncio
from contextlib import asynccontextmanager

from .consulService.BLConsul import register_consul_service, unregister_consul_service

from fastapi import FastAPI
from app.routers import main_router
from app.sql import models
from app.sql import database
from app.routers import rabbitmq
from global_variables.global_variables import update_system_resources_periodically, set_rabbitmq_status, get_rabbitmq_status
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
    """Configuration to be executed when FastAPI server starts."""
    try:
        logger.info("Creating database tables")
        async with database.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error while creating database tables: {e}")
        raise  # Rethrow the exception if you want the startup to fail

    register_consul_service()

    try:
        logger.info("Subscribing to RabbitMQ channels")
        await rabbitmq.subscribe_channel()
        asyncio.create_task(rabbitmq.subscribe_command_payment_check())
        logger.info("RabbitMQ channels subscribed successfully")
    except Exception as e:
        logger.error(f"Error while subscribing to RabbitMQ channels: {e}")
        raise  # Rethrow if you want to halt the startup

    try:
        asyncio.create_task(rabbitmq.subscribe_payment_check())
        try:
            task = asyncio.create_task(update_system_resources_periodically(15))
        except Exception as e:
            logger.error(f"Error al monitorear recursos del sistema: {e}")

        data = {
            "message": "INFO - Servicio Orders inicializado correctamente"
        }
        logger.info("Payment check subscription task created")
    except Exception as e:
        logger.error(f"Error while creating payment check subscription task: {e}")
        raise  # Rethrow if necessary

@app.on_event("shutdown")
async def shutdown_event():
    logger.debug("Dentro del shutdown")
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
        port=8009,
        log_config='logging.ini'
    )
    logger.debug("App finished as script")


