# -*- coding: utf-8 -*-
"""Functions that interact with the database."""
import logging
from datetime import datetime
from typing import Optional
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from . import models
from passlib.context import CryptContext
from routers import rabbitmq
from . import schemas

logger = logging.getLogger(__name__)


# READ
async def get_list(db: AsyncSession, model):
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


async def get_element_by_username_and_pass(db: AsyncSession, model, username, password):
    """Retrieve any DB element by id."""
    if username is None:
        return None
    stmt = select(model).filter(model.username == username, model.password == password)
    element = await get_element_statement_result(db, stmt)
    return element


# DELETE
async def delete_element_by_id(db: AsyncSession, model, element_id):
    """Delete any DB element by id."""
    element = await get_element_by_id(db, model, element_id)
    if element is not None:
        await db.delete(element)
        await db.commit()
    return element


async def get_client_list(db: AsyncSession):
    """Load all the clients from the database."""
    stmt = select(models.User)
    clients = await get_list_statement_result(db, stmt)
    return clients


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Hash the password using PBKDF2 (SHA-256)."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify the password."""
    return pwd_context.verify(plain_password, hashed_password)


async def create_user(db: AsyncSession, user: schemas.UserCreate):
    """Persist a new user into the database with hashed password using PBKDF2."""

    # Hash the password
    hashed_password = get_password_hash(user.password)

    # Check if any user with role 'admin' exists in the database
    result = await db.execute(select(models.User).where(models.User.rol == 'admin'))
    admin_exists = result.scalars().first()

    # Determine the role for the new user
    user_role = 'admin' if user.username == 'admin' and not admin_exists else 'user'

    # Create the user with the assigned role
    db_user = models.User(
        username=user.username,
        email=user.email,
        password=hashed_password,
        address=user.address,
        postal_code=int(user.postal_code),
        rol=user_role,
        creation_date=datetime.now()
    )

    # Add the new user to the database
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)  # Refresh to get the auto-generated ID
    data = {
        "id_client": db_user.id
    }
    message_body = json.dumps(data)
    routing_key = "client.created"
    await rabbitmq.publish(message_body, routing_key)
    return db_user


async def update_user(db: AsyncSession, client_id, client):
    """Modify a client of the database."""
    db_user = await get_user_by_id(db, client_id)
    db_user.email = client.email
    db_user.address = client.address
    db_user.postal_code = int(client.postal_code)
    await db.commit()
    await db.refresh(db_user)
    data = {
        "id_client": db_user.id
    }
    message_body = json.dumps(data)
    routing_key = "client.updated"
    await rabbitmq.publish(message_body, routing_key)
    return db_user



async def get_user_by_username(db: AsyncSession, username: str) -> Optional[models.User]:
    """Get a user by username."""
    result = await db.execute(select(models.User).filter(models.User.username == username))
    return result.scalars().first()


async def get_client_by_username_and_pass(db: AsyncSession, username, password):
    """Load a client from the database."""
    return await get_element_by_username_and_pass(db, models.Client, username, password)


async def get_user_by_id(db: AsyncSession, id_client: int) -> Optional[models.User]:
    """Get a user by their ID."""
    result = await db.execute(select(models.User).filter(models.User.id == id_client))
    return result.scalars().first()

