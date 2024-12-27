# -*- coding: utf-8 -*-
"""Application dependency injector."""
import logging

logger = logging.getLogger(__name__)

MY_MACHINE = None


# Database #########################################################################################
async def get_db():
    """Generates SQLAlchemy database sessions and closes them when finished."""
    from app.sql.database import SessionLocal
    logger.debug("Starting SQLAlchemy session...")
    async with SessionLocal() as db:
        try:
            logger.debug("Yielding SQLAlchemy session...")
            yield db
            logger.debug("Committing SQLAlchemy session...")
            await db.commit()
        except Exception as e:
            logger.error(f"Error in database session: {e}")
            await db.rollback()
            raise
        finally:
            logger.debug("Closing SQLAlchemy session...")
            await db.close()


# Machine #########################################################################################
async def get_machine():
    """Returns the machine object (creates it the first time its executed)."""
    logger.debug("Getting machine")
    global MY_MACHINE
    if MY_MACHINE is None:
        from app.business_logic.async_machine import Machine
        MY_MACHINE = await Machine.create()
    return MY_MACHINE


# asyncio.create_task(get_machine())
# asyncio.run(init_machine())
