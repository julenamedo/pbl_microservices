# -*- coding: utf-8 -*-
"""Classes for Request/Response schema definitions."""
# pylint: disable=too-few-public-methods
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict  # pylint: disable=no-name-in-module




class Message(BaseModel):
    """Message schema definition."""
    detail: Optional[str] = Field(example="error or success message")


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
    id_client: Optional[int] = Field(
        None,
        description="ID of the user",
        example=1
    )


class UserAddress(UserAddressBase):
    """Schema for representing UserAddress."""
    id_client: int

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
    id_client: Optional[int] = Field(
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
    id_client: int

    class Config:
        orm_mode = True