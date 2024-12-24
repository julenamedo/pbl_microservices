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
    number_of_pieces: int = Field(
        description="Number of pieces to manufacture for the new order",
        default=None,
        example=10
    )
    description: str = Field(
        description="Human readable description for the order",
        default="No description",
        example="CompanyX order on 2022-01-20"
    )

    #  pieces = relationship("Piece", lazy="joined")


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


class PieceBase(BaseModel):
    """Piece base schema definition."""
    id: int = Field(
        description="Piece identifier (Primary key)",
        example="1"
    )
    manufacturing_date: Optional[datetime] = Field(
        description="Date when piece has been manufactured",
        example="2022-07-22T17:32:32.193211"
    )
    status: str = Field(
        description="Current status of the piece",
        default="Queued",
        example="Manufactured"
    )


class Piece(PieceBase):
    """Piece schema definition."""
    model_config = ConfigDict(from_attributes=True)  # ORM mode ON
    order: Optional[Order] = Field(description="Order where the piece belongs to")

    #class Config:
    #    """ORM configuration."""
    #    orm_mode = True


class MachineStatusResponse(BaseModel):
    """machine status schema definition."""
    status: str = Field(
        description="Machine's current status",
        default=None,
        example="Waiting"
    )
    working_piece: Optional[int] = Field(
        description="Current working piece id. None if not working piece.",
        example=1
    )
    queue: List[int] = Field(description="Queued piece ids")


class UserAddressBase(BaseModel):
    """Base schema for UserAddress."""
    address: Optional[str] = Field(
        None,
        description="Address for the user",
        example="Calle Falsa 123"
    )
    zip_code: Optional[int] = Field(
        None,
        description="Postal code for the address",
        example=12345
    )


class UserAddressCreate(UserAddressBase):
    """Schema for creating a UserAddress."""
    user_id: Optional[int] = Field(
        None,
        description="ID of the user",
        example=1
    )


class UserAddress(UserAddressBase):
    """Schema for representing UserAddress."""
    user_id: int

    class Config:
        orm_mode = True


class DeliveryBase(BaseModel):
    """Base schema for Delivery."""
    status: Optional[str] = Field(
        None,
        description="Status of the delivery",
        example="IN_PROGRESS"
    )


class DeliveryCreate(BaseModel):
    """Schema for creating a Delivery."""
    user_id: Optional[int] = Field(
        None,
        description="ID of the user creating the delivery",
        example=1
    )
    order_id: int = Field(
        description="Unique ID of the order",
        example=123
    )


class DeliveryUpdate(BaseModel):
    """Schema for updating a Delivery."""
    status: Optional[str] = Field(
        None,
        description="New status of the delivery",
        example="COMPLETED"
    )


class Delivery(DeliveryBase):
    """Schema for representing Delivery."""
    order_id: int
    user_id: int

    class Config:
        orm_mode = True