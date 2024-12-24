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
from app.dependencies import get_db, get_machine
from app.sql import crud
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

def verify_access_token(token: str):
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


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
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
        return verify_access_token(token)

    except HTTPException as e:
        # Manejar específicamente las excepciones HTTP y relanzarlas
        logger.error(f"HTTPException in get_current_user: {e.detail}")
        logger.error(f"JWTError in get_current_user: {str(e)}")
        data = {
            "message": "ERROR - Error in get_current_user"
        }
        message_body = json.dumps(data)
        routing_key = "orders.verify.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise e

    except JWTError as e:
        # Manejar específicamente errores relacionados al token
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
        # Loguear errores inesperados y evitar que escalen a un error 500
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
    db: AsyncSession = Depends(get_db),

):
    """Create single order endpoint."""
    logger.debug("POST '/order' endpoint called.")
    order_schema.id_client=current_user["user_id"]
    db_order = await crud.create_order_from_schema(db, order_schema)
    data = {
        "id_order": db_order.id,
        "id_client": db_order.id_client,
        "movement": -(db_order.number_of_pieces)
    }
    message_body = json.dumps(data)
    routing_key = "events.order.created.pending"
    await rabbitmq.publish(message_body, routing_key)
    await rabbitmq_publish_logs.publish_log("order " + str(db_order.id) + " needs the balance to be checked", "logs.info.order")

    # Retornar la respuesta final
    return {"detail": "Order created successfully", "order_id": db_order.id}

@router.get(
    "/order/{order_id}",
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
        db: AsyncSession = Depends(get_db),
        current_user: Dict = Depends(get_current_user)
):
    """Retrieve single order by id"""
    logger.debug("GET '/order/%i' endpoint called.", order_id)
    order = await crud.get_order(db, order_id)
    data = {
        "message": "INFO - Order obtained by id"
    }
    message_body = json.dumps(data)
    routing_key = "logs.info.order"
    await rabbitmq_publish_logs.publish_log(message_body, routing_key)
    if not order:
        raise_and_log_error(logger, status.HTTP_404_NOT_FOUND, f"Order {order_id} not found")
    return order


@router.delete(
    "/order/{order_id}",
    summary="Delete order",
    responses={
        status.HTTP_200_OK: {
            "model": schemas.Order,
            "description": "Order successfully deleted."
        },
        status.HTTP_404_NOT_FOUND: {
            "model": schemas.Message, "description": "Order not found"
        }
    },
    tags=["Order"]
)
async def remove_order_by_id(
        order_id: int,
        db: AsyncSession = Depends(get_db),
current_user: Dict = Depends(get_current_user)
        #my_machine: Machine = Depends(get_machine)
):
    """Remove order"""

    if current_user["role"] != "admin":
        logger.warning("Access denied for user_id: %s with role: %s", current_user["user_id"], current_user["role"])
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: only admins can delete orders."
        )

    logger.debug("DELETE '/order/%i' endpoint called.", order_id)
    order = await crud.get_order(db, order_id)
    data = {
        "message": "INFO - Order deleted"
    }
    message_body = json.dumps(data)
    routing_key = "logs.info.order"
    await rabbitmq_publish_logs.publish_log(message_body, routing_key)
    logger.debug(order)
    if not order:
        raise_and_log_error(logger, status.HTTP_404_NOT_FOUND, f"Order {order_id} not found")
    #await my_machine.remove_pieces_from_queue(order.pieces)
    try:
        response= requests.delete(f"http://localhost:8001/machine_order/{order_id}")
        if response.status_code != status.HTTP_200_OK:
            raise Exception
        return await crud.delete_order(db, order_id)

    except Exception as exc:  #catchear el error si no se puede eliminar o acceder a la api de machine
        print("Ha habido un error creando la pieza")
        raise_and_log_error(logger, status.HTTP_409_CONFLICT, f"Error creating order: {exc}")


@router.put(
    "/order/{order_id}",
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
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update order endpoint for admins only."""

    # Verificar si el usuario tiene el rol de administrador
    if current_user["role"] != "admin":
        logger.warning("Access denied for user_id: %s with role: %s", current_user["user_id"], current_user["role"])
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: only admins can update orders."
        )

    # Convertir los datos de actualización en un diccionario excluyendo valores no definidos
    update_data = order_update.dict(exclude_unset=True)

    # Intentar actualizar la orden usando el método del CRUD
    updated_order = await crud.update_order(db, order_id, update_data)
    if not updated_order:
        raise_and_log_error(logger, status.HTTP_404_NOT_FOUND, f"Order {order_id} not found")

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
        db: AsyncSession = Depends(get_db),
        current_user: Dict = Depends(get_current_user)
):
    """Retrieve sagas history"""
    logger.debug("GET '/order/sagashistory/%i' endpoint called.", order_id)
    logs = await crud.get_sagas_history(db, order_id)
    if not logs:
        data = {
            "message": "ERROR - Logs not found"
        }
        message_body = json.dumps(data)
        routing_key = "logs.error.order"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise_and_log_error(logger, status.HTTP_404_NOT_FOUND)
    data = {
        "message": "INFO - Log obtained"
    }
    message_body = json.dumps(data)
    routing_key = "logs.info.order"
    await rabbitmq_publish_logs.publish_log(message_body, routing_key)
    return logs
