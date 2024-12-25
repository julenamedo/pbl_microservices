# -*- coding: utf-8 -*-
"""Database models definitions. Table representations as class."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, TEXT, ForeignKey, Float
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
                # fields = "{}='{}'".format(column.name, getattr(self, column.name))
            else:
                fields = f"{fields}, {column.name}='{getattr(self, column.name)}'"
                # fields = "{}, {}='{}'".format(fields, column.name, getattr(self, column.name))
        return f"<{self.__class__.__name__}({fields})>"
        # return "<{}({})>".format(self.__class__.__name__, fields)

    @staticmethod
    def list_as_dict(items):
        """Returns list of items as dict."""
        return [i.as_dict() for i in items]

    def as_dict(self):
        """Return the item as dict."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Payment(Base):
    __tablename__ = "payment"

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_client = Column(Integer, unique=True, nullable=False)  # Ensures unique id_client for each payment entry
    balance = Column(Float, default=0.0)  # Default balance set to 0.0
    creation_date = Column(DateTime, default=datetime.utcnow)  # Auto-filled timestamp

    def __repr__(self):
        return f"<Payment(id={self.id}, id_client={self.id_client}, balance={self.balance})>"
