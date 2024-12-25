# -*- coding: utf-8 -*-
"""FastAPI router definitions."""
import logging
from typing import List
import json
import fastapi
from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.business_logic.async_machine import Machine
from app.dependencies import get_db, get_machine
from app.sql import crud
from app.routers import rabbitmq, rabbitmq_publish_logs
from .auth import PUBLIC_KEY, ALGORITHM
from app.sql import schemas
from .router_utils import raise_and_log_error
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.routers.auth import create_access_token
from app.sql import crud, schemas, models
from app.dependencies import get_db
from jose import JWTError, jwt
from passlib.context import CryptContext
from global_variables.global_variables import rabbitmq_working, system_values
from global_variables.global_variables import get_rabbitmq_status
from fastapi.responses import JSONResponse


logger = logging.getLogger(__name__)
router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@router.get("/health", tags=["Health check"])
async def health_check():
    """
    Endpoint de health check para verificar el estado de RabbitMQ y los recursos del sistema.
    """
    try:
        # Verificar si RabbitMQ está funcionando

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


#Auth module
security = HTTPBearer(auto_error=False,)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
with open("/keys/pub.pem", "r") as pub_file:
    PUBLIC_KEY = pub_file.read()
ALGORITHM = "RS256"


def verify_access_token(token: str):
    """Verifica la validez del token JWT"""
    if not token:
        data = {
            "message": "ERROR - You don't have permissions"
        }
        message_body = json.dumps(data)
        routing_key = "client.verify.error"
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
        routing_key = "client.verify.info"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        return payload  # Devuelve el payload, que contiene la información del usuario
    except JWTError as e:
        # Loggear el error específico antes de lanzar la excepción
        logger.error(f"JWTError en la verificación del token: {str(e)}")
        data = {
            "message": "ERROR - Error on token verification"
        }
        message_body = json.dumps(data)
        routing_key = "client.verify.error"
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
            routing_key = "client.verify.error"
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
        routing_key = "client.verify.info"
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
        routing_key = "client.verify.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise e

    except JWTError as e:
        # Manejar específicamente errores relacionados al token
        logger.error(f"JWTError in get_current_user: {str(e)}")
        data = {
            "message": "ERROR - Error in get_current_user"
        }
        message_body = json.dumps(data)
        routing_key = "client.verify.error"
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


@router.post("/register", response_model=schemas.UserData)
async def register(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    try:
        # Verifica si el usuario ya existe
        existing_user = await crud.get_user_by_username(db, user.username)
        if existing_user:
            data = {
                "message": "ERROR - Username already registered"
            }
            message_body = json.dumps(data)
            routing_key = "client.register.error"
            await rabbitmq_publish_logs.publish_log(message_body, routing_key)
            raise HTTPException(status_code=400, detail="Username already registered")

        # Crea el nuevo usuario
        new_user = await crud.create_user(db, user)
        data = {
            "message": "INFO - Client created"
        }
        message_body = json.dumps(data)
        routing_key = "client.register.info"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        return new_user

    except Exception as e:
        logger.error(f"Error during registration: {str(e)}")
        data = {
            "message": "ERROR - Error creating client"
        }
        message_body = json.dumps(data)
        routing_key = "client.register.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/login")
async def login(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    db_user = await crud.get_user_by_username(db, user.username)

    if not db_user or not crud.verify_password(user.password, db_user.password):
        logger.error("Invalid credentials, missing id_client or username.")
        raise fastapi.HTTPException(status_code=400, detail="Invalid credentials")


    # Crear el access token (con expiración corta)
    access_token = create_access_token(
        data={"username": db_user.username, "id_client": db_user.id, "role": db_user.rol}
    )

    # Crear el refresh token (con expiración larga)
    refresh_token = create_access_token(
        data={"username": db_user.username, "id_client": db_user.id, "role": db_user.rol}
    )

    # Retornar ambos tokens
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.post("/refresh")
async def refresh_token(token: str, db: AsyncSession = Depends(get_db)):
    try:
        logger.debug(f"Received token for refresh: {token}")
        # Decodificar el refresh token
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=[ALGORITHM])
        id_client = payload.get("id_client")
        username = payload.get("username")

        if id_client is None or username is None:
            logger.error("Invalid refresh token, missing id_client or username.")
            data = {
                "message": "ERROR - Invalid refresh token, missing id_client or username"
            }
            message_body = json.dumps(data)
            routing_key = "client.refresh.error"
            await rabbitmq_publish_logs.publish_log(message_body, routing_key)
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        # Verificar si el usuario aún existe en la base de datos
        db_user = await crud.get_user_by_id(db, id_client)
        if not db_user:
            logger.error(f"User with ID {id_client} not found.")
            data = {
                "message": "ERROR - User not found."
            }
            message_body = json.dumps(data)
            routing_key = "client.refresh.error"
            await rabbitmq_publish_logs.publish_log(message_body, routing_key)
            raise HTTPException(status_code=404, detail="User not found")

        # Generar un nuevo access token
        data = {
            "message": "INFO - access_token refreshed"
        }
        message_body = json.dumps(data)
        routing_key = "client.refresh.info"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        access_token = create_access_token(
            data={"username": username, "id_client": id_client}
        )

        logger.debug("New access token generated successfully.")
        return {"access_token": access_token, "token_type": "bearer"}

    except JWTError as jwt_error:
        logger.error(f"JWT decoding error: {str(jwt_error)}")
        data = {
            "message": "ERROR - Invalid refresh token"
        }
        message_body = json.dumps(data)
        routing_key = "client.refresh.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    except Exception as e:
        logger.error(f"Unhandled error during refresh token: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.put("/change-password", response_model=schemas.UserData)
async def change_password(
    current_password: str,
    new_password: str,
    id_client: int = None,  # Parámetro opcional
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    # Si `id_client` se proporciona, verificar que sea admin o coincida con el ID del usuario autenticado
    if id_client:
        if user.get("role") != "admin" and user.get("id_client") != id_client:
            data = {
                "message": "ERROR - Not authorized"
            }
            message_body = json.dumps(data)
            routing_key = "client.change_password.error"
            await rabbitmq_publish_logs.publish_log(message_body, routing_key)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    else:
        # Si no se proporciona `id_client`, usar el ID del usuario autenticado
        id_client = user.get("id_client")

    # Obtener el usuario objetivo
    db_user = await crud.get_user_by_id(db, id_client)
    if not db_user:
        data = {
            "message": "ERROR - User not found"
        }
        message_body = json.dumps(data)
        routing_key = "client.change_password.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Si no es admin, verificar la contraseña actual
    if user.get("role") != "admin" and not crud.verify_password(current_password, db_user.password):
        data = {
            "message": "ERROR - Incorrect current password"
        }
        message_body = json.dumps(data)
        routing_key = "client.change_password.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect current password")

    # Cambiar la contraseña
    db_user.password = crud.get_password_hash(new_password)
    await db.commit()
    await db.refresh(db_user)
    data = {
        "message": "INFO - Client password updated"
    }
    message_body = json.dumps(data)
    routing_key = "client.change_password.info"
    await rabbitmq_publish_logs.publish_log(message_body, routing_key)
    return db_user


@router.delete("/delete/{id_client}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    id_client: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    # Verificar que el usuario autenticado sea administrador
    if user.get("role") != "admin":
        data = {
            "message": "ERROR - Not authorized"
        }
        message_body = json.dumps(data)
        routing_key = "client.delete.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Obtener el usuario objetivo
    db_user = await crud.get_user_by_id(db, id_client)
    if not db_user:
        data = {
            "message": "ERROR - User not found"
        }
        message_body = json.dumps(data)
        routing_key = "client.delete.error"
        await rabbitmq_publish_logs.publish_log(message_body, routing_key)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Eliminar al usuario
    await db.delete(db_user)
    await db.commit()
    data = {
        "message": "INFO - Client deleted"
    }
    message_body = json.dumps(data)
    routing_key = "client.delete.info"
    await rabbitmq_publish_logs.publish_log(message_body, routing_key)
    return {"message": "User deleted successfully"}

