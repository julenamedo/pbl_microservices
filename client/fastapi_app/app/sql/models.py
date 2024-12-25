# -*- coding: utf-8 -*-
"""Database models definitions. Table representations as class."""
from sqlalchemy import Column, DateTime, Integer, String, TEXT, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class BaseModel(Base):
    """Base database table representation to reuse."""
    __abstract__ = True
    creation_date = Column(DateTime(timezone=True), server_default=func.now())
    update_date = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        fields = ""
        for column in self.__table__.columns:
            if fields == "":
                fields = f"{column.name}='{getattr(self, column.name)}'"
            else:
                fields = f"{fields}, {column.name}='{getattr(self, column.name)}'"
        return f"<{self.__class__.__name__}({fields})>"
    @staticmethod
    def list_as_dict(items):
        """Returns list of items as dict."""
        return [i.as_dict() for i in items]

    def as_dict(self):
        """Return the item as dict."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class User(Base):

    __tablename__ = "users"  # Cambié el nombre a 'users' para que coincida con tu tabla

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(256), nullable=False)
    username = Column(String(256), nullable=False, unique=True)
    password = Column(String(256), nullable=False)
    address = Column(String(256), nullable=False)
    zip_code = Column(Integer, nullable=False)
    creation_date = Column(DateTime(timezone=True), server_default=func.now())
    rol = Column(String(50), nullable=False, default="user")  # Añadir la columna 'rol'

    def as_dict(self):
        """Return the user item as dict."""
        return {
            "id": self.id,
            "username": self.username,
            "creation_date": self.creation_date
        }