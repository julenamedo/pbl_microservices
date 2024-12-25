# -*- coding: utf-8 -*-
"""Classes for Request/Response schema definitions."""
# pylint: disable=too-few-public-methods
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict  # pylint: disable=no-name-in-module


class Message(BaseModel):
    """Message schema definition."""
    detail: Optional[str] = Field(example="error or success message")


class OrderBase(BaseModel):
    """Order base schema definition."""
    number_of_pieces_a: int = Field(
        description="Number of pieces of A type to manufacture for the new order",
        default=None,
        example=10
    )
    number_of_pieces_b: int = Field(
        description="Number of pieces of B type to manufacture for the new order",
        default=None,
        example=10
    )
    description: str = Field(
        description="Human readable description for the order",
        default="No description",
        example="CompanyX order on 2022-01-20"
    )
    id_client: int = Field(
        description="Identifier of the client.",
        default=1,
        example=1
    )


class OrderUpdate(BaseModel):
    """Esquema para actualizar una orden con campos opcionales."""
    number_of_pieces_a: Optional[int] = Field(
        description="Number of pieces of A type to manufacture for the order",
        example=10
    )
    number_of_pieces_b: Optional[int] = Field(
        description="Number of pieces of B type to manufacture for the order",
        example=10
    )
    description: Optional[str] = Field(
        description="Human-readable description for the order",
        example="CompanyX order on 2022-01-20"
    )
    id_client: Optional[int] = Field(
        description="Identifier of the client",
        example=1
    )
    status: Optional[str] = Field(
        description="Current status of the order",
        example="InProgress"
    )


class Order(OrderBase):
    """Order schema definition."""
    model_config = ConfigDict(from_attributes=True)  # ORM mode ON
    id: int = Field(
        description="Primary key/identifier of the order.",
        default=None,
        example=1
    )
    status: str = Field(
        description="Current status of the order",
        default="Created",
        example="Finished"
    )


class OrderPost(OrderBase):
    """Schema definition to create a new order."""


class CatalogBase(BaseModel):
    """Catalog base schema definition."""
    id: int = Field()
    piece_type: str = Field()
    price: str = Field()


class SagasHistoryBase(BaseModel):
    """Sagas history base schema definition."""
    id: int = Field()
    id_order: int = Field()
    status: str = Field()
