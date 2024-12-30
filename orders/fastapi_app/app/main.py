# -*- coding: utf-8 -*-
"""Main file to start FastAPI application."""
import logging.config
import os
import asyncio
import json
from contextlib import asynccontextmanager

from .consulService.BLConsul import register_consul_service, unregister_consul_service

from fastapi import FastAPI
from app.routers import main_router, rabbitmq, rabbitmq_publish_logs
from app.sql import models
from app.sql import database, crud
import global_variables
from global_variables.global_variables import update_system_resources_periodically, set_rabbitmq_status, get_rabbitmq_status
# Configure logging ################################################################################
print("Name: ", __name__)
logging.config.fileConfig(os.path.join(os.path.dirname(__file__), 'logging.ini'))
logger = logging.getLogger(__name__)


# Main #############################################################################################
# If application is run as script, execute uvicorn on port 8000

# OpenAPI Documentation ############################################################################
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")
logger.info("Running app version %s", APP_VERSION)
DESCRIPTION = """
Monolithic manufacturing order application.
"""

tag_metadata = [

    {
        "name": "Order",
        "description": "Endpoints to **CREATE**, **READ**, **UPDATE** or **DELETE (CANCEL)** orders.",
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
        """Configuration to be executed when FastAPI server starts."""
        logger.info("Creating database tables")
        async with database.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        db = database.SessionLocal()
        _ = await crud.create_catalog_from_schema(db)
        await db.close()
        await rabbitmq.subscribe_channel()
        await rabbitmq_publish_logs.subscribe_channel()
        logger.info("Se ha suscrito")

        register_consul_service()

        asyncio.create_task(rabbitmq.subscribe_delivery_checked_order_cancel())
        asyncio.create_task(rabbitmq.subscribe_order_finished())
        asyncio.create_task(rabbitmq.subscribe_delivering())
        asyncio.create_task(rabbitmq.subscribe_produced())
        asyncio.create_task(rabbitmq.subscribe_warehouse_checked_order_cancel())
        asyncio.create_task(rabbitmq.subscribe_payment_reverted_order_cancel())
        asyncio.create_task(rabbitmq.subscribe_delivery_reverted_order_cancel())
        asyncio.create_task(rabbitmq.subscribe_delivery_cancel())
        asyncio.create_task(rabbitmq.subscribe_payment_checked_order_cancel())
        asyncio.create_task(rabbitmq.subscribe_command_payment_checked())
        asyncio.create_task(rabbitmq.subscribe_delivery_checked())
        asyncio.create_task(update_system_resources_periodically(15))

        data = {
            "message": "INFO - Servicio Orders inicializado correctamente"
        }
        message_body = json.dumps(data)
        routing_key = "orders.startup.info"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
    except Exception as e:
        logger.error(f"Error al monitorear recursos del sistema: {e}")
        data = {
            "message": "ERROR - Error al inicializar el servicio Order"
        }
        message_body = json.dumps(data)
        routing_key = "orders.startup.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)


    logger.info("Se ha enviado")

@app.on_event("shutdown")
async def shutdown_event():
    data = {
        "message": "INFO - Servicio Order desregistrado de Consul"
    }
    message_body = json.dumps(data)
    routing_key = "orders.shutdown.info"
    await rabbitmq_publish_logs.publish_log(message_body, routing_key)
    unregister_consul_service()

if __name__ == "__main__":
    import uvicorn

    logger.debug("App run as script")
    print("Starting uvicorn...")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8008,
        log_config='logging.ini'
    )


    logger.debug("App finished as script")
