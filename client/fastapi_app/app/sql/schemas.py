# -*- coding: utf-8 -*-
"""Classes for Request/Response schema definitions."""
# pylint: disable=too-few-public-methods
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict  # pylint: disable=no-name-in-module


class Message(BaseModel):
    """Message schema definition."""
    detail: Optional[str] = Field(example="error or success message")


class UserBase(BaseModel):
    username: str = Field(
        description="The username of the client.",
        default=None,
        example="julen"
    )
    email: str = Field(
        description="The email of the client.",
        default="example@alumni.mondragon.edu",
        example="example@alumni.mondragon.edu"
    )
    address: str = Field(
        description="The address of the client.",
        default="calle postas",
        example="calle postas"
    )
    postal_code: str = Field(
        description="The postal code of the client.",
        default="01002",
        example="01002"
    )
    rol: str = Field(
        description="The role of the client.",
        default="user",
        example="admin"
    )


class UserCreate(UserBase):
    """Schema definition to create a new client."""
    password: str = Field(
        description="The password of the client.",
        default="12345678aA@",
        example="12345678aA@"
    )


class UserData(UserBase):
    """User data model for output."""
    id: int
    creation_date: datetime

    class Config:
        orm_mode = True  # Esto es necesario para que Pydantic pueda leer los objetos SQLAlchemy


class UserInDB(UserBase):
    """Internal model with hashed password."""
    hashed_password: str
    creation_date: datetime
    id: int

    class Config:
        orm_mode = True