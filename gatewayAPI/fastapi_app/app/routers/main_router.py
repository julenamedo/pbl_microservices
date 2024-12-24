# -*- coding: utf-8 -*-
"""FastAPI router definitions."""
import logging
from typing import List
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.business_logic.async_machine import Machine
from app.dependencies import get_db, get_machine
from app.sql import crud
from ..sql import schemas
from .router_utils import raise_and_log_error


from fastapi import FastAPI, Request
import httpx

logger = logging.getLogger(__name__)


app = FastAPI()
router = APIRouter()
# URLs de los servicios
MACHINE_URL = "http://host.docker.internal:8001"
ORDER_URL = "http://host.docker.internal:8002"
DELIVERY_URL = "http://host.docker.internal:8003"
PAYMENT_URL = "http://host.docker.internal:8005"

@router.post("/create_order/",tags=["Order"])
async def create_order(order_schema: schemas.OrderPost):
    # Llama a la API de Order para crear un pedido
    order_data = order_schema.dict()
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{ORDER_URL}/order", json=order_data)
        return response.json()

@router.post("/create_piece/")
async def create_piece(piece_data: dict):
    # Llama a la API de Machine para crear una pieza
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{MACHINE_URL}/pieces/", json=piece_data)
        return response.json()


@router.post("/deposit_money/", tags=["Payment"])
async def deposit_money(cantidad: float):
    try:
        # Llama a la API de Payment para procesar un depósito
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{PAYMENT_URL}/deposit?cantidad={cantidad}")

        # Si el status code no es exitoso, lanza un error
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Error en el servicio de Payment: {response.text}"
            )

        return response.json()

    except httpx.RequestError as exc:
        # Error relacionado con la conexión o la solicitud
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error de conexión al servicio de Payment: {str(exc)}"
        )


@router.post("/start_delivery")
async def start_delivery(delivery_data: dict):
    # Llama a la API de Delivery para iniciar la entrega
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{DELIVERY_URL}/deliveries/", json=delivery_data)
        return response.json()


@router.get("/balance",tags=["Payment"])
async def balance():
    # Llama a la API de Delivery para iniciar la entrega
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{PAYMENT_URL}/balance")
        return response.json()


@router.get(
    "/order/{order_id}",
    summary="Retrieve single order by id through the gateway",
    responses={
        status.HTTP_200_OK: {
            "model": schemas.Order,
            "description": "Requested Order."
        },
        status.HTTP_404_NOT_FOUND: {
            "model": schemas.Message, "description": "Order not found"
        }
    },
    tags=["Order"]
)
async def get_single_order(order_id: int):
    """Retrieve single order by id through the gateway"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{ORDER_URL}/order/{order_id}")

    # Si el status code no es 200, lanza un error
    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found"
        )
    elif response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error en el servicio de Order: {response.text}"
        )

    return response.json()

@router.delete(
    "/order/{order_id}",
    summary="Delete order through the gateway",
    responses={
        status.HTTP_200_OK: {
            "description": "Order successfully deleted."
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Order not found"
        },
        status.HTTP_409_CONFLICT: {
            "description": "Error removing order from machine."
        }
    },
    tags=["Order"]
)
async def delete_order_via_gateway(order_id: int):
    """Delete order through the gateway, interacting with Order and Machine services"""
    try:

        async with httpx.AsyncClient() as client:
            response = await client.delete(f"{ORDER_URL}/order/{order_id}")


        if response.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found in Order service."
            )
        elif response.status_code == status.HTTP_409_CONFLICT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Error deleting order {order_id} from Machine service."
            )
        elif response.status_code != status.HTTP_200_OK:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Error in Order service: {response.text}"
            )

        return {"message": f"Order {order_id} successfully deleted."}

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error connecting to Order service: {str(exc)}"
        )

# Corre el servidor con Uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)