# -*- coding: utf-8 -*-
"""Functions that interact with the database."""
import logging
import json
from datetime import datetime
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from .database import SessionLocal
from ..routers.rabbitmq import publish
from . import models
from sqlalchemy import update

logger = logging.getLogger(__name__)


# READ
async def get_list(db: AsyncSession, model):
    """Retrieve a list of elements from database"""
    result = await db.execute(select(model))
    item_list = result.unique().scalars().all()
    return item_list


async def get_list_statement_result(db: AsyncSession, stmt):
    """Execute given statement and return list of items."""
    result = await db.execute(stmt)
    item_list = result.unique().scalars().all()
    return item_list


async def get_element_statement_result(db: AsyncSession, stmt):
    """Execute statement and return a single items"""
    result = await db.execute(stmt)
    item = result.scalar()
    return item


async def get_element_by_id(db: AsyncSession, model, element_id):
    """Retrieve any DB element by id."""
    if element_id is None:
        return None
    element = await db.get(model, element_id)
    return element


# DELETE
async def delete_element_by_id(db: AsyncSession, model, element_id):
    """Delete any DB element by id."""
    element = await get_element_by_id(db, model, element_id)
    if element is not None:
        await db.delete(element)
        await db.commit()
    return element


# Warehouse functions ##################################################################################
async def get_piece(db: AsyncSession, piece_id):
    return await get_element_by_id(db, models.Piece, piece_id)


async def create_piece(db: AsyncSession, piece):
    """Persist a new piece into the database."""
    db_piece = models.Piece(
        piece_type=piece.piece_type,
        status_piece=piece.status_piece,
        id_order=piece.id_order,
        id_client=piece.id_client
    )
    db.add(db_piece)
    await db.commit()
    await db.refresh(db_piece)
    data = {
        "id_piece": db_piece.id_piece
    }
    message_body = json.dumps(data)
    if piece.piece_type == "A":
        routing_key = "piece_a.requested"
    elif piece.piece_type == "B":
        routing_key = "piece_b.requested"
    await publish(message_body, routing_key)
    return db_piece


async def change_piece_status(db: AsyncSession, piece_id, status):
    """Change piece status in the database."""
    db_piece = await get_piece(db, piece_id)
    db_piece.status_piece = status
    if status == models.Piece.STATUS_PRODUCED:
        db_piece.manufacturing_date = func.now()
    await db.commit()
    await db.refresh(db_piece)
    return db_piece


async def change_piece_order_id(db: AsyncSession, piece_id, order_id):
    """Change piece order ID in the database."""
    db_piece = await get_piece(db, piece_id)
    db_piece.id_order = order_id
    await db.commit()
    await db.refresh(db_piece)
    return db_piece


async def get_all_pieces(db: AsyncSession):
    pieces = await get_list(db, models.Piece)
    return pieces


async def get_order_pieces(db: AsyncSession, order_id):
    stmt = select(models.Piece).where(models.Piece.id_order == order_id)
    pieces = await get_list_statement_result(db, stmt)
    return pieces


async def get_pieces_by_type(db: AsyncSession, piece_type):
    stmt = select(models.Piece).where(models.Piece.piece_type == piece_type)
    pieces = await get_list_statement_result(db, stmt)
    return pieces


async def get_order_pieces_by_type(db: AsyncSession, order_id, piece_type):
    stmt = select(models.Piece).where(
        and_(
            models.Piece.id_order == order_id,
            models.Piece.piece_type == piece_type
        )
    )
    pieces = await get_list_statement_result(db, stmt)
    return pieces