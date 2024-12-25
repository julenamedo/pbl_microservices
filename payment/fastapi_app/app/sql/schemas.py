# -*- coding: utf-8 -*-
"""Classes for Request/Response schema definitions."""
# pylint: disable=too-few-public-methods
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict  # pylint: disable=no-name-in-module


class Message(BaseModel):
    """Message schema definition."""
    detail: Optional[str] = Field(example="error or success message")


class BalanceResponse(BaseModel):
    id_client: int
    balance: float = Field(..., description="The user's current balance")

class BalanceUpdate(BaseModel):
    amount: float = Field(..., description="Amount to add or subtract from the balance")



class BalanceUpdate(BaseModel):
    """Schema for updating the user's balance."""
    amount: float = Field(..., description="Amount to add or subtract from the balance")
