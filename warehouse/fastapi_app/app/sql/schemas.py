# -*- coding: utf-8 -*-
"""Classes for Request/Response schema definitions."""
# pylint: disable=too-few-public-methods
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict  # pylint: disable=no-name-in-module


class Message(BaseModel):
    detail: Optional[str] = Field(example="error or success message")


class PieceBase(BaseModel):
    id_order: int = Field(description="Order associated to the piece.")
    id_client: int = Field(description="Client associated to the piece.")
    piece_type: str = Field(
        description="Piece type.",
        example="A"
    )
    manufacturing_date: Optional[datetime] = Field(
        description="Date piece manufactured.",
        example="2022-07-22T17:32:32.193211"
    )
    status_piece: str = Field(
        description="Status of the piece.",
        default="Queued",
        example="Manufactured"
    )


class Piece(PieceBase):
    """Piece schema definition."""
    id_piece: int = Field(
        description="Piece id",
        example="1"
    )

    class Config:
        orm_mode = True
