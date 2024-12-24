# -*- coding: utf-8 -*-
"""Main file to start FastAPI application."""
import logging.config
import os
from contextlib import asynccontextmanager
import json
from .consulService.BLConsul import register_consul_service
from .consulService.BLConsul import unregister_consul_service

from fastapi import FastAPI
from app.routers import main_router
from app.routers import rabbitmq, rabbitmq_publish_logs
from app.sql import models
from app.sql import database
import asyncio
import global_variables
from global_variables.global_variables import update_system_resources_periodically, set_rabbitmq_status, get_rabbitmq_status
# Configure logging ################################################################################
print("Name: ", __name__)
logging.config.fileConfig(os.path.join(os.path.dirname(__file__), 'logging.ini'))
logger = logging.getLogger(__name__)


# OpenAPI Documentation ############################################################################
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")
logger.info("Running app version %s", APP_VERSION)
DESCRIPTION = """
Monolithic client application.
"""

tag_metadata = [

    {
        "name": "Client",
        "description": "Endpoints related to clients",
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
        logger.info("Creating database tables")
        async with database.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        await rabbitmq.subscribe_channel()
        await rabbitmq_publish_logs.subscribe_channel()
        register_consul_service()
        task = asyncio.create_task(update_system_resources_periodically(15))
        data = {
            "message": "INFO - Servicio Client inicializado"
        }
        message_body = json.dumps(data)
        routing_key = "client.startup.info"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
    except Exception as e:
        logger.error(f"Error al monitorear recursos del sistema: {e}")
        data = {
            "message": "ERROR - Error al inicializar el servicio Client"
        }
        message_body = json.dumps(data)
        routing_key = "client.startup.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)

    logger.info("Se ha enviado")

@app.on_event("shutdown")
async def shutdown_event():
    data = {
        "message": "INFO - Servicio Client desregistrado de Consul"
    }
    message_body = json.dumps(data)
    routing_key = "client.shutdown.info"
    await rabbitmq_publish_logs.publish_log(message_body, routing_key)
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
        port=8007,
        log_config='logging.ini'
    )
    logger.debug("App finished as script")
