# -*- coding: utf-8 -*-
"""FastAPI router definitions."""
import logging
import json
import httpx
import requests
from typing import List
from fastapi import APIRouter, Depends, status, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic.json_schema import models_json_schema
from sqlalchemy.ext.asyncio import AsyncSession
from app import dependencies
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

async def verify_access_token(token: str):
    """Verifica la validez del token JWT"""
    if not token:
        data = {
            "message": "ERROR - You don't have permissions"
        }
        message_body = json.dumps(data)
        routing_key = "warehouse.verify.error"
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
        routing_key = "warehouse.verify.info"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        return payload  # Devuelve el payload, que contiene la información del usuario
    except JWTError as e:
        # Loggear el error específico antes de lanzar la excepción
        logger.error(f"JWTError en la verificación del token: {str(e)}")
        data = {
            "message": "ERROR - Error on token verification"
        }
        message_body = json.dumps(data)
        routing_key = "warehouse.verify.error"
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


@router.get(
    "/warehouse",
    summary="Retrieve catalog of pieces",
    responses={
        status.HTTP_200_OK: {
            "model": schemas.Piece,
            "description": "Requested Pieces."
        },
        status.HTTP_404_NOT_FOUND: {
            "model": schemas.Message, "description": "Warehouse not found"
        }
    },
    tags=['Warehouse']
)
async def get_warehouse(
    id_order: int = Query(None, description="Order ID"),
    piece_type: str = Query(None, description="Piece type"),
    db: AsyncSession = Depends(dependencies.get_db),
    current_user: Dict = Depends(get_current_user),

):

    try:
        if current_user["role"] != "admin":
            logger.warning("Access denied for id_client: %s with role: %s", current_user["id_client"], current_user["role"])
            data = {
                "message": "ERROR - You don't have permissions"
            }
            message_body = json.dumps(data)
            routing_key = "warehouse.get_warehouse.error"
            await rabbitmq_publish_logs.publish_log(message_body, routing_key)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden: only admins can delete orders."
            )
        logger.debug("GET '/warehouse' endpoint called.")

        if id_order is None and piece_type is None:
            order_list = await crud.get_all_pieces(db)
        elif id_order is not None and piece_type is None:
            if id_order == -1:
                id_order = None
            order_list = await crud.get_order_pieces(db, id_order)
        elif id_order is None and piece_type is not None:
            order_list = await crud.get_pieces_by_type(db, piece_type)
        elif id_order is not None and piece_type is not None:
            if id_order == -1:
                id_order = None
            order_list = await crud.get_order_pieces_by_type(db, id_order, piece_type)

        data = {
            "message": "INFO - Piece list obtained"
        }
        message_body = json.dumps(data)
        routing_key = "warehouse.get_warehouse.info"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        return order_list

    except Exception as exc:
        print("Error retrieving pieces catalog")
        data = {
            "message": "ERROR - Error obtaining pieces list"
        }
        message_body = json.dumps(data)
        routing_key = "warehouse.get_warehouse.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise_and_log_error(logger, status.HTTP_409_CONFLICT, f"Error obtaining order list: {exc}")

