# -*- coding: utf-8 -*-
"""FastAPI router definitions."""
import logging
import os

from typing import List
from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.security import HTTPBearer, OAuth2PasswordBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from app import dependencies
from app.sql import crud
from app.sql import schemas
from app.routers import rabbitmq, rabbitmq_publish_logs
import json
from app.routers.router_utils import raise_and_log_error
from global_variables.global_variables import rabbitmq_working, system_values
from global_variables.global_variables import get_rabbitmq_status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()


security = HTTPBearer(auto_error=False,)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
with open("/keys/pub.pem", "r") as pub_file:
    PUBLIC_KEY = pub_file.read()
ALGORITHM = "RS256"


  # Ensure this imports get_current_user with the token verification

router = APIRouter()

async def verify_access_token(token: str):
    """Verifica la validez del token JWT"""
    if not token:
        data = {
            "message": "ERROR - You don't have permissions"
        }
        message_body = json.dumps(data)
        routing_key = "payment.verify.error"
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
        routing_key = "payment.verify.info"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        return payload  # Devuelve el payload, que contiene la información del usuario
    except JWTError as e:
        # Loggear el error específico antes de lanzar la excepción
        logger.error(f"JWTError en la verificación del token: {str(e)}")
        data = {
            "message": "ERROR - Error on token verification"
        }
        message_body = json.dumps(data)
        routing_key = "payment.verify.error"
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
            routing_key = "payment.verify.error"
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
        routing_key = "payment.verify.info"
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
        routing_key = "payment.verify.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise e

    except JWTError as e:
        # Manejar específicamente errores relacionados al token
        logger.error(f"JWTError in get_current_user: {str(e)}")
        data = {
            "message": "ERROR - Error in get_current_user"
        }
        message_body = json.dumps(data)
        routing_key = "payment.verify.error"
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
# Route to get the balance for the current user
@router.get("/balance", response_model=schemas.BalanceResponse, summary="Get balance")
async def get_balance(
        id_client: int = None,  # Parámetro opcional
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(dependencies.get_db)
):
    """Retrieve balance for the authenticated user or a specific user if admin."""
    # Si se proporciona `id_client`, verificar permisos
    if id_client:
        if current_user.get("role") != "admin":
            data = {
                "message": "ERROR - You don't have permissions"
            }
            message_body = json.dumps(data)
            routing_key = "payment.get_balance.error"
            await rabbitmq_publish_logs.publish_log(message_body, routing_key)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Admins only.")
    else:
        # Si no se proporciona, usar el ID del usuario autenticado
        id_client = current_user["id_client"]

    # Obtener el balance del usuario
    payment = await crud.get_balance_by_id_client(db, id_client)
    if not payment:
        data = {
            "message": "ERROR - user balance not found"
        }
        message_body = json.dumps(data)
        routing_key = "payment.get_balance.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User balance not found")
    data = {
        "message": "INFO - user balance retrieved"
    }
    message_body = json.dumps(data)
    routing_key = "payment.get_balance.info"
    await rabbitmq_publish_logs.publish_log(message_body, routing_key)
    return schemas.BalanceResponse(id_client=payment.id_client, balance=payment.balance)


# Ruta para actualizar el balance
@router.put("/balance", response_model=schemas.BalanceResponse, summary="Update balance")
async def update_balance(
        update_data: schemas.BalanceUpdate,
        id_client: int = None,  # Parámetro opcional
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(dependencies.get_db)
):
    """Update balance for the authenticated user or a specific user if admin."""
    # Si se proporciona `id_client`, verificar permisos
    if id_client:
        if current_user.get("role") != "admin":
            data = {
                "message": "ERROR - You don't have permissions"
            }
            message_body = json.dumps(data)
            routing_key = "payment.update_balance.error"
            await rabbitmq_publish_logs.publish_log(message_body, routing_key)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Admins only.")
    else:
        # Si no se proporciona, usar el ID del usuario autenticado
        id_client = current_user["id_client"]

    # Verificar que el monto sea positivo
    if update_data.amount < 0:
        data = {
            "message": "ERROR - Charging the user is not allowed. Amount must be positive."
        }
        message_body = json.dumps(data)
        routing_key = "payment.update_balance.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Charging the user is not allowed. Amount must be positive."
        )

    # Actualizar el balance
    new_balance, success = await crud.update_balance_by_id_client(db, id_client, update_data.amount)

    if not success:
        data = {
            "message": "ERROR - Insufficient funds"
        }
        message_body = json.dumps(data)
        routing_key = "payment.update_balance.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds")

    data = {
        "message": "INFO - user balance updated"
    }
    message_body = json.dumps(data)
    routing_key = "payment.update_balance.info"
    await rabbitmq_publish_logs.publish_log(message_body, routing_key)
    return schemas.BalanceResponse(id_client=id_client, balance=new_balance)