# -*- coding: utf-8 -*-
"""Database session configuration."""
import os
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

SQLALCHEMY_DATABASE_URL = os.getenv(
    'SQLALCHEMY_DATABASE_URL',
    "sqlite+aiosqlite:///./monolithic.db"
)

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession,
    future=True,
    expire_on_commit=False
)

Base = declarative_base()
