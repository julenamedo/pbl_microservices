# -*- coding: utf-8 -*-
"""Functions that interact with the database."""
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from . import models
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, or_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, delete, select
from sqlalchemy.sql import or_, case
from sqlalchemy.exc import NoResultFound
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import logging
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException, status

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def create_address(db: AsyncSession, id_client: int, address: str, zip_code: int):
    """Create a new address for a user, ensuring there is no existing address."""
    # Check if an address already exists for the user
    existing_address = await db.execute(
        select(models.UserAddress).where(models.UserAddress.id_client == id_client)
    )
    existing_address = existing_address.scalars().first()

    if existing_address:
        # Update the existing address
        existing_address.address = address
        existing_address.zip_code = zip_code
        await db.commit()
        await db.refresh(existing_address)
        logger.debug("Address updated for id_client %s with address: %s", id_client, address)
        return existing_address

    # Create the new address
    new_address = models.UserAddress(id_client=id_client, address=address, zip_code=zip_code)
    db.add(new_address)
    await db.commit()
    await db.refresh(new_address)
    logger.debug("Address created for id_client %s with address: %s", id_client, address)
    return new_address


async def get_list_statement_result(db: AsyncSession, stmt):
    """Execute given statement and return list of items."""
    result = await db.execute(stmt)
    item_list = result.unique().scalars().all()
    return item_list


async def create_delivery(db: AsyncSession, order_id: int, id_client: int, delivery_status: str):
    """Create a new delivery for a user, ensuring there is no existing delivery for the same order_id."""
    try:
        # Check if a delivery already exists for the order_id
        existing_delivery = await db.execute(
            select(models.Delivery).where(models.Delivery.order_id == order_id)
        )
        existing_delivery = existing_delivery.scalars().first()

        if existing_delivery:
            # Optionally update the status or other fields of the existing delivery
            existing_delivery.status = existing_delivery.status  # Reset status if needed
            existing_delivery.id_client = id_client  # Update the user ID if applicable
            await db.commit()
            await db.refresh(existing_delivery)
            logger.debug("Delivery updated for order_id %s with id_client: %s", order_id, id_client)
            return existing_delivery

        # Create a new delivery if no existing one is found
        new_delivery = models.Delivery(order_id=order_id, id_client=id_client, status=delivery_status)
        db.add(new_delivery)
        await db.commit()
        await db.refresh(new_delivery)
        logger.debug("Delivery created with order_id %s, id_client: %s, and status: %s", order_id, id_client,
                     delivery_status)
        return new_delivery

    except SQLAlchemyError as e:
        # Catch and log SQLAlchemy-specific errors
        logger.error("Database error during delivery creation: %s", str(e))
        print(f"Database error: {e}")  # Optional: Replace with logger if preferred
        raise HTTPException(status_code=500, detail="Database error occurred")

    except Exception as e:
        # Catch and log any other unexpected exceptions
        logger.error("Unexpected error during delivery creation: %s", str(e))
        print(f"Unexpected error: {e}")  # Optional: Replace with logger if preferred
        raise HTTPException(status_code=500, detail="Unexpected error occurred")


async def update_address(db: AsyncSession, id_client: int, address: Optional[str], zip_code: Optional[int]):
    """Actualizar la dirección para un usuario."""
    async with db.begin():
        stmt = (
            update(models.UserAddress)
            .where(models.UserAddress.id_client == id_client)
            .values(
                address=address if address else models.UserAddress.address,
                zip_code=zip_code if zip_code else models.UserAddress.zip_code
            )
            .execution_options(synchronize_session="fetch")
        )
        result = await db.execute(stmt)
        await db.commit()

    if result.rowcount == 0:
        logger.debug("No address found for id_client %s. Update skipped.", id_client)
        return None

    logger.debug("Address updated for id_client %s", id_client)
    return await get_address_by_id_client(db, id_client)


async def check_address(db: AsyncSession, id_client):
    """Persist a new client into the database."""

    address = await get_address_by_id_client(db, id_client)

    provincia = address.zip_code // 1000  # Extraer código de provincia del código postal
    if (provincia == 1 or provincia == 20 or provincia == 48):
        address_check = True
    else:
        address_check = False
    return address_check


async def get_delivery_by_order(db: AsyncSession, order_id: int):
    """Fetch a single delivery by order_id."""
    stmt = select(models.Delivery).where(models.Delivery.order_id == order_id)
    result = await db.execute(stmt)
    delivery = result.scalars().first()
    if not delivery:
        logger.debug("No delivery found for order_id %s", order_id)
    return delivery


async def update_delivery(db: AsyncSession, order_id: int, new_status: str):
    stmt = (
        update(models.Delivery)
        .where(models.Delivery.order_id == order_id)
        .values(status=new_status)
        .execution_options(synchronize_session="fetch")
    )
    await db.execute(stmt)
    await db.commit()  # Asegúrate de confirmar la transacción
    return await get_delivery_by_order_id(db, order_id)




async def delete_address(db: AsyncSession, id_client: int):
    """Eliminar una dirección por id_client."""
    async with db.begin():
        stmt = delete(models.UserAddress).where(models.UserAddress.id_client == id_client)
        result = await db.execute(stmt)
        await db.commit()

    if result.rowcount == 0:
        logger.debug("No address found for id_client %s. Delete skipped.", id_client)
        return False

    logger.debug("Address for id_client %s deleted successfully", id_client)
    return True


async def delete_delivery(db: AsyncSession, order_id: int):
    """Eliminar un delivery por order_id."""
    async with db.begin():
        stmt = delete(models.Delivery).where(models.Delivery.order_id == order_id)
        result = await db.execute(stmt)
        await db.commit()

    if result.rowcount == 0:
        logger.debug("No delivery found for order_id %s. Delete skipped.", order_id)
        return False

    logger.debug("Delivery with order_id %s deleted successfully", order_id)
    return True


async def get_address_by_id_client(db: AsyncSession, id_client: int):
    """Obtener una dirección por id_client."""
    result = await db.execute(select(models.UserAddress).where(models.UserAddress.id_client == id_client))
    return result.scalars().first()


async def get_delivery_by_order_id(db: AsyncSession, order_id: int):
    """Obtener un delivery por order_id."""
    result = await db.execute(select(models.Delivery).where(models.Delivery.order_id == order_id))
    return result.scalars().first()
