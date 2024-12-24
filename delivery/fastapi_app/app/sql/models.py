# -*- coding: utf-8 -*-
"""Database models definitions. Table representations as class."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, TEXT, ForeignKey, Text, CheckConstraint
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, CheckConstraint
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


class Order(BaseModel):
    """order database table representation."""
    STATUS_CREATED = "Created"
    STATUS_CANCELED = "Canceled"
    STATUS_FINISHED = "Finished"
    STATUS_DELIVERED = "Delivered"
    STATUS_PAYMENT_PENDING = "PaymentPending"
    STATUS_PAYMENT_DONE = "PaymentDone"
    STATUS_PAYMENT_CANCELED = "PaymentCanceled"

    __tablename__ = "manufacturing_order"
    id = Column(Integer, primary_key=True)
    number_of_pieces = Column(Integer, nullable=False)
    description = Column(TEXT, nullable=False, default="No description")
    status = Column(String(256), nullable=False, default=STATUS_CREATED)

    pieces = relationship("Piece", back_populates="order", lazy="joined")

    def as_dict(self):
        """Return the order item as dict."""
        dictionary = super().as_dict()
        dictionary['pieces'] = [i.as_dict() for i in self.pieces]
        return dictionary


class Piece(BaseModel):
    """Piece database table representation."""
    STATUS_CREATED = "Created"
    STATUS_CANCELLED = "Cancelled"
    STATUS_QUEUED = "Queued"
    STATUS_MANUFACTURING = "Manufacturing"
    STATUS_MANUFACTURED = "Manufactured"

    __tablename__ = "piece"
    id = Column(Integer, primary_key=True)
    manufacturing_date = Column(DateTime(timezone=True), server_default=None)
    status = Column(String(256), default=STATUS_QUEUED)
    order_id = Column(
        Integer,
        ForeignKey('manufacturing_order.id', ondelete='cascade'),
        nullable=True)

    order = relationship('Order', back_populates='pieces', lazy="joined")


class Delivery(Base):
    STATUS_IN_PROGRESS = "in progress"
    STATUS_CREATED = "created"
    STATUS_CANCELED = "canceled"
    STATUS_COMPLETED = "completed"

    __tablename__ = "deliveries"

    user_id = Column(Integer, nullable=False)
    order_id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(
        Text,
        nullable=False,
        default=STATUS_IN_PROGRESS,  # Estado inicial permitido
    )

class UserAddress(Base):
    __tablename__ = "user_address"

    user_id = Column(Integer, primary_key=True)  # ID único del usuario
    address = Column(String(255), nullable=False)  # Dirección de entrega
    zip_code = Column(Integer, nullable=False)  # Código postal

    def __repr__(self):
        return f"<UserAddress(user_id={self.user_id}, address={self.address}, zip_code={self.zip_code})>"