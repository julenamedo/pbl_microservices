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
from urllib.parse import unquote

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

api_urls = {
    "machine": MACHINE_URL,
    "order": ORDER_URL,
    "delivery": DELIVERY_URL,
    "payment": PAYMENT_URL
}

@router.post("/{nombre_api}/{metodo:path}", tags=["Gateway"])
async def post_api(nombre_api: str, metodo: str, request: dict):

    if nombre_api not in api_urls:
        raise HTTPException(status_code=400, detail="API no soportada")

    decoded_metodo = unquote(metodo)

    target_url = api_urls[nombre_api]

    async with httpx.AsyncClient() as client:
        response = await client.post(f"{target_url}/{decoded_metodo}", json=request)
        return response.json()

@router.get("/{nombre_api}/{metodo:path}", tags=["Gateway"])
async def get_api(nombre_api: str, metodo: str):

    if nombre_api not in api_urls:
        raise HTTPException(status_code=400, detail="API no soportada")

    #logger.debug(metodo)
    #decoded_metodo = unquote(metodo)
    #logger.debug(decoded_metodo)

    target_url = api_urls[nombre_api]

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{target_url}/{metodo}")
        return response.json()

@router.delete("/{nombre_api}/{metodo:path}", tags=["Gateway"])
async def get_api(nombre_api: str, metodo: str):

    if nombre_api not in api_urls:
        raise HTTPException(status_code=400, detail="API no soportada")

    #logger.debug(metodo)
    #decoded_metodo = unquote(metodo)
    #logger.debug(decoded_metodo)

    target_url = api_urls[nombre_api]

    async with httpx.AsyncClient() as client:
        response = await client.delete(f"{target_url}/{metodo}")
        return response.json()


# Corre el servidor con Uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)