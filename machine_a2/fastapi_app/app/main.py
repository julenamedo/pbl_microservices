# -*- coding: utf-8 -*-
"""Main file to start FastAPI application."""
import logging.config
import os
import json
from contextlib import asynccontextmanager

from .consulService.BLConsul import register_consul_service, unregister_consul_service

from fastapi import FastAPI
from app.sql import models
from app.sql import database
from app.routers import main_router
from app.routers import rabbitmq
from app.routers import rabbitmq_publish_logs
import asyncio
from global_variables.global_variables import update_system_resources_periodically, set_rabbitmq_status, get_rabbitmq_status

# Configure logging ################################################################################
print("Name: ", __name__)
logging.config.fileConfig(os.path.join(os.path.dirname(__file__), 'logging.ini'))
logger = logging.getLogger(__name__)



# OpenAPI Documentation ############################################################################
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")
logger.info("Running app version %s", APP_VERSION)
DESCRIPTION = """
Machine A2 application.
"""

tag_metadata = [

    {
        "name": "Machine_A2",
        "description": "Endpoints related to machines",
    },

]

app = FastAPI(
    redoc_url=None,  # disable redoc documentation.
    title="FastAPI - Machine A2 app",
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
        async with database.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        await rabbitmq.subscribe_channel()
        await rabbitmq_publish_logs.subscribe_channel()

        register_consul_service()

        asyncio.create_task(rabbitmq.subscribe())
        try:
            task = asyncio.create_task(update_system_resources_periodically(15))
        except Exception as e:
            logger.error(f"Error al monitorear recursos del sistema: {e}")
        data = {
            "message": "INFO - Servicio Machine A1 inicializado correctamente"
        }
        message_body = json.dumps(data)
        routing_key = "machine_a2.startup.info"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
    except:
        data = {
            "message": "ERROR - Error al inicializar servicio Machine A2"
        }
        message_body = json.dumps(data)
        routing_key = "machine_a2.startup.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)

@app.on_event("shutdown")
async def shutdown_event():
    data = {
        "message": "INFO - Servicio Machine A1 desregistrado de Consul"
    }
    message_body = json.dumps(data)
    routing_key = "machine_a2.shutdown.info"
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
        port=8002,
        log_config='logging.ini'
    )
    logger.debug("App finished as script")
