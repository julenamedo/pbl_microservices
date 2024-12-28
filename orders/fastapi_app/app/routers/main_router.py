# -*- coding: utf-8 -*-
"""FastAPI router definitions."""
import logging
import json
import httpx
import requests
from typing import List
from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic.json_schema import models_json_schema
from sqlalchemy.ext.asyncio import AsyncSession
from app import dependencies
from app.sql import crud, models, schemas
from ..sql import schemas
from app.routers import rabbitmq_publish_logs, rabbitmq
from .router_utils import raise_and_log_error
from typing import Dict
from global_variables.global_variables import rabbitmq_working, system_values
from global_variables.global_variables import get_rabbitmq_status
from fastapi.responses import JSONResponse

with open("/keys/priv.pem", "r") as priv_file:
    PRIVATE_KEY = priv_file.read()

with open("/keys/pub.pem", "r") as pub_file:
    PUBLIC_KEY = pub_file.read()
security = HTTPBearer(auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
logger = logging.getLogger(__name__)
router = APIRouter()

# Claves de JWT y configuración


ALGORITHM = "RS256"

async def verify_access_token(token: str):
    """Verifica la validez del token JWT"""
    if not token:
        data = {
            "message": "ERROR - You don't have permissions"
        }
        message_body = json.dumps(data)
        routing_key = "orders.verify.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token no encontrado o inválido."
        )
    try:
        # Decodifica el token usando la clave pública y el algoritmo especificado
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=[ALGORITHM])
        logger.debug("Token verificado exitosamente.")
        data = {
            "message": "INFO - Token generated"
        }
        message_body = json.dumps(data)
        routing_key = "orders.verify.info"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        return payload  # Devuelve el payload, que contiene la información del usuario
    except JWTError as e:
        # Loggear el error específico antes de lanzar la excepción
        logger.error(f"JWTError en la verificación del token: {str(e)}")
        data = {
            "message": "ERROR - Error on token verification"
        }
        message_body = json.dumps(data)
        routing_key = "orders.verify.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token inválido o expirado."
        )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        # Verificar si no hay credenciales en la cabecera
        if credentials is None or not credentials.credentials:
            logger.warning("No token provided in Authorization header.")
            data = {
                "message": "ERROR - Failed to authenticate client"
            }
            message_body = json.dumps(data)
            routing_key = "orders.verify.error"
            await rabbitmq_publish_logs.publish_log(message_body, routing_key)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No token provided."
            )

        # Verificar el token extraído
        token = credentials.credentials
        logger.debug("Token extracted, proceeding to verify.")
        data = {
            "message": "INFO - Token extracted, proceeding to verify"
        }
        message_body = json.dumps(data)
        routing_key = "orders.verify.info"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)

        # Add await here
        payload = await verify_access_token(token)
        return payload

    except HTTPException as e:
        logger.error(f"HTTPException in get_current_user: {e.detail}")
        data = {
            "message": "ERROR - Error in get_current_user"
        }
        message_body = json.dumps(data)
        routing_key = "orders.verify.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise e

    except JWTError as e:
        logger.error(f"JWTError in get_current_user: {str(e)}")
        data = {
            "message": "ERROR - Error in get_current_user"
        }
        message_body = json.dumps(data)
        routing_key = "orders.verify.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token inválido o expirado."
        )

    except Exception as e:
        logger.error(f"Unexpected error in get_current_user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Error in token verification."
        )

# Orders ###########################################################################################
# Endpoint de health check
@router.get("/health", tags=["Health check"])
async def health_check():
    """
    Endpoint de health check para verificar el estado de RabbitMQ y los recursos del sistema.
    """
    try:
        # Verificar si RabbitMQ está funcionando
        if not get_rabbitmq_status():
            logger.error("RabbitMQ no está funcionando correctamente.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RabbitMQ no está disponible"
            )

        cpu = system_values["CPU"]
        memory = system_values["Memory"]

        # Registra los valores de los recursos
        logger.info("System resources: CPU = %s%%, Memory = %s%%", cpu, memory)

        # Verificar si el uso de CPU o memoria es demasiado alto
        MAX_CPU_USAGE = 90  # 90% de uso de CPU
        MAX_MEMORY_USAGE = 90  # 90% de uso de memoria

        if cpu > MAX_CPU_USAGE:
            logger.error("Uso de CPU demasiado alto: %s%%", cpu)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Uso de CPU demasiado alto: {cpu}%"
            )

        if memory > MAX_MEMORY_USAGE:
            logger.error("Uso de memoria demasiado alto: %s%%", memory)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Uso de memoria demasiado alto: {memory}%"
            )

        # Si todo está bien, devolver un mensaje de éxito
        return JSONResponse(content={
            "status": "OK",
            "cpu_usage": cpu,
            "memory_usage": memory
        }, status_code=status.HTTP_200_OK)

    except Exception as e:
        # Captura y loguea excepciones generales
        logger.error(f"Error inesperado en health_check: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno en el servidor."
        )


@router.post(
    "/create_order",
    summary="Create single order",
    status_code=status.HTTP_201_CREATED,
    tags=["Order"]
)
async def create_order(
    order_schema: schemas.OrderPost,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(dependencies.get_db),

):
    """Create single order endpoint."""
    logger.debug("POST '/order' endpoint called.")
    try:
        order_schema.id_client = current_user["id_client"]
        db_order = await crud.create_order_from_schema(db, order_schema)
        data = {
            "message": "INFO - Order created"
        }
        message_body = json.dumps(data)
        routing_key = "orders.create_order.info"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)

        # Retornar la respuesta final
        return {"detail": "Order created successfully", "order_id": db_order.id}
    except Exception as exc:
        data = {
            "message": "ERROR - Error creating order"
        }
        message_body = json.dumps(data)
        routing_key = "orders.create_order.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise_and_log_error(logger, status.HTTP_409_CONFLICT, f"Error creating order: {exc}")

@router.get(
    "/order/retrieve/{order_id}",
    summary="Retrieve single order by id",
    responses={
        status.HTTP_200_OK: {
            "model": schemas.Order,
            "description": "Requested Order."
        },
        status.HTTP_404_NOT_FOUND: {
            "model": schemas.Message, "description": "Order not found"
        }
    },
    tags=['Order']
)
async def get_single_order(
        order_id: int,
        db: AsyncSession = Depends(dependencies.get_db),
        current_user: Dict = Depends(get_current_user)
):
    """Retrieve single order by id"""
    logger.debug("GET '/order/%i' endpoint called.", order_id)
    order = await crud.get_order(db, order_id)
    data = {
        "message": "INFO - Order obtained by id"
    }
    message_body = json.dumps(data)
    routing_key = "orders.get_single_order.info"
    await rabbitmq_publish_logs.publish_log(message_body, routing_key)
    if not order:
        raise_and_log_error(logger, status.HTTP_404_NOT_FOUND, f"Order {order_id} not found")
        data = {
            "message": "ERROR - Order not found"
        }
        message_body = json.dumps(data)
        routing_key = "orders.get_single_order.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
    return order


@router.post(
    "/order/cancel/{id_order}",
    response_model=schemas.Order,
    summary="Cancel single order",
    status_code=status.HTTP_200_OK,
    tags=["Order"]
)
async def cancel_order(
        order_id: int,
        db: AsyncSession = Depends(dependencies.get_db)
):
    """Cancel single order endpoint."""
    logger.debug("POST '/order/cancel/%i' endpoint called.", order_id)
    try:
        order = await crud.get_order(db, order_id)
        if (order.status == models.Order.STATUS_DELIVERY_PENDING) or (
                order.status == models.Order.STATUS_PAYMENT_PENDING) or (
                order.status == models.Order.STATUS_DELIVERY_CANCELING):
            raise_and_log_error(logger, status.HTTP_409_CONFLICT,
                                f"Order can't be canceled as it is being processed yet, please try again later.")
        elif (order.status == models.Order.STATUS_QUEUED):
            db_order = await crud.cancel_order(db, order_id)
            data = {
                "message": "INFO - Order cancelation started"
            }
            message_body = json.dumps(data)
            routing_key = "orders.cancel_order.info"
            await rabbitmq_publish_logs.publish_log(message_body, routing_key)
            return db_order
        else:
            raise_and_log_error(logger, status.HTTP_409_CONFLICT, f"Unknown error at order cancelation.")
    except Exception as exc:
        data = {
            "message": "ERROR - Error canceling the order"
        }
        message_body = json.dumps(data)
        routing_key = "orders.cancel_order.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise_and_log_error(logger, status.HTTP_409_CONFLICT, f"Error canceling order: {exc}")


@router.put(
    "/order/update/{order_id}",
    summary="Update order",
    response_model=schemas.Order,
    responses={
        status.HTTP_200_OK: {
            "model": schemas.Order,
            "description": "Order successfully updated."
        },
        status.HTTP_404_NOT_FOUND: {
            "model": schemas.Message, "description": "Order not found"
        },
        status.HTTP_403_FORBIDDEN: {
            "model": schemas.Message, "description": "Access forbidden"
        }
    },
    tags=["Order"]
)
async def update_order(
    order_id: int,
    order_update: schemas.OrderUpdate,
    db: AsyncSession = Depends(dependencies.get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update order endpoint for admins only."""

    # Verificar si el usuario tiene el rol de administrador
    if current_user["role"] != "admin":
        logger.warning("Access denied for id_client: %s with role: %s", current_user["id_client"], current_user["role"])
        data = {
            "message": "ERROR - You don't have permissions"
        }
        message_body = json.dumps(data)
        routing_key = "orders.update_order.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: only admins can update orders."
        )

    # Convertir los datos de actualización en un diccionario excluyendo valores no definidos
    update_data = order_update.dict(exclude_unset=True)

    # Intentar actualizar la orden usando el método del CRUD
    updated_order = await crud.update_order(db, order_id, update_data)
    if not updated_order:
        data = {
            "message": "ERROR - Order to be updated not found"
        }
        message_body = json.dumps(data)
        routing_key = "orders.update_order.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise_and_log_error(logger, status.HTTP_404_NOT_FOUND, f"Order {order_id} not found")

    data = {
        "message": "INFO - Order updated"
    }
    message_body = json.dumps(data)
    routing_key = "orders.update_order.info"
    await rabbitmq_publish_logs.publish_log(message_body, routing_key)
    return updated_order


@router.get(
    "/order/sagashistory/{order_id}",
    summary="Retrieve sagas history of a certain order",
    responses={
        status.HTTP_200_OK: {
            "model": schemas.SagasHistoryBase,
            "description": "Requested sagas history."
        },
        status.HTTP_404_NOT_FOUND: {
            "model": schemas.Message, "description": "Sagas history not found"
        }
    },
    tags=['Order']
)
async def get_sagas_history(
        order_id: int,
        db: AsyncSession = Depends(dependencies.get_db)
):
    """Retrieve sagas history"""
    logger.debug("GET '/order/sagashistory/%i' endpoint called.", order_id)
    logs = await crud.get_sagas_history(db, order_id)
    if not logs:
        data = {
            "message": "ERROR - Saga history not found"
        }
        message_body = json.dumps(data)
        routing_key = "orders.get_sagas_history.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise_and_log_error(logger, status.HTTP_404_NOT_FOUND)
    data = {
        "message": "INFO - Saga history obtained"
    }
    message_body = json.dumps(data)
    routing_key = "orders.get_sagas_history.info"
    await rabbitmq_publish_logs.publish_log(message_body, routing_key)
    return logs


@router.get(
    "/order/catalog",
    summary="Retrieve catalog",
    responses={
        status.HTTP_200_OK: {
            "model": schemas.CatalogBase,
            "description": "Requested catalog."
        },
        status.HTTP_404_NOT_FOUND: {
            "model": schemas.Message, "description": "Catalog not found"
        }
    },
    tags=['Order']
)
async def get_catalog(
        db: AsyncSession = Depends(dependencies.get_db),
        current_user: dict = Depends(get_current_user)
):
    """Retrieve catalog"""
    logger.debug("GET '/order/catalog' endpoint called.")
    db_catalog = await crud.get_catalog(db)
    if not db_catalog:
        data = {
            "message": "ERROR - Catalog not found"
        }
        message_body = json.dumps(data)
        routing_key = "orders.get_catalog.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise_and_log_error(logger, status.HTTP_404_NOT_FOUND)
    data = {
        "message": "INFO - Catalog obtained"
    }
    message_body = json.dumps(data)
    routing_key = "orders.get_catalog.info"
    await rabbitmq_publish_logs.publish_log(message_body, routing_key)
    return db_catalog
