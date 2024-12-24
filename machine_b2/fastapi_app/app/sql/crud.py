# -*- coding: utf-8 -*-
"""Functions that interact with the database."""
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

logger = logging.getLogger(__name__)


machine_status = "Machine Status: Idle"

async def set_status_of_machine(status):
    global machine_status
    machine_status = status

async def get_status_of_machine():
    return machine_status