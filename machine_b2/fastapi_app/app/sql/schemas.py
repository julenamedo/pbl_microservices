# -*- coding: utf-8 -*-
"""Classes for Request/Response schema definitions."""
# pylint: disable=too-few-public-methods
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict  # pylint: disable=no-name-in-module


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
