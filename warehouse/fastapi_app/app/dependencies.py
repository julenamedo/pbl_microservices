# -*- coding: utf-8 -*-
"""Application dependency injector."""
import logging

import logging

logger = logging.getLogger(__name__)

MY_MACHINE = None


# Database #########################################################################################
async def get_db():
    """Generates database sessions and closes them when finished."""
    from app.sql.database import SessionLocal  # pylint: disable=import-outside-toplevel
    logger.debug("Getting database SessionLocal")
    async with SessionLocal() as db:
        try:
            yield db
            await db.commit()
        except Exception as e:
            logger.error(f"Error en la sesión de base de datos: {e}")
            await db.rollback()
            raise  # Relanza la excepción para asegurar que sea gestionada en la llamada
        finally:
            await db.close()

