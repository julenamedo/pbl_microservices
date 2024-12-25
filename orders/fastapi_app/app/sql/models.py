# -*- coding: utf-8 -*-
"""Database models definitions. Table representations as class."""
from sqlalchemy import Column, DateTime, Integer, String, TEXT, Float, ForeignKey
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
    STATUS_DELIVERY_PENDING = "DeliveryPending"
    STATUS_PAYMENT_PENDING = "PaymentPending"
    STATUS_DELIVERY_CANCELING = "DeliveryCanceling"
    STATUS_CANCELED = "Canceled"
    STATUS_QUEUED = "Queued"
    STATUS_PRODUCED = "Produced"
    STATUS_DELIVERING = "Delivering"
    STATUS_DELIVERED = "Delivered"
    STATUS_ORDER_CANCEL_DELIVERY_PENDING = "OrderCancelDeliveryPending"
    STATUS_ORDER_CANCEL_PAYMENT_PENDING = "OrderCancelPaymentPending"
    STATUS_ORDER_CANCEL_WAREHOUSE_PENDING = "OrderCancelWarehousePending"
    STATUS_ORDER_CANCEL_PAYMENT_RECHARGING = "OrderCancelPaymentRecharging"
    STATUS_ORDER_CANCEL_DELIVERY_REDELIVERING = "OrderCancelDeliveryRedelivering"

    __tablename__ = "manufacturing_order"
    id = Column(Integer, primary_key=True)
    number_of_pieces_a = Column(Integer, nullable=False)
    number_of_pieces_b = Column(Integer, nullable=False)
    description = Column(TEXT, nullable=False, default="No description")
    status = Column(String(256), nullable=False)
    id_client = Column(Integer, nullable=False)
    pieces = relationship("Piece", back_populates="order", lazy="joined")

    def as_dict(self):
        """Return the order item as dict."""
        dictionary = super().as_dict()
        dictionary['pieces'] = [i.as_dict() for i in self.pieces]
        return dictionary


class Catalog(BaseModel):
    """Catalog database table representation."""
    __tablename__ = "catalog"
    piece_type = Column(String(256), primary_key=True)
    description = Column(String(256), nullable=False)
    price = Column(Float, nullable=False)


class SagasHistory(BaseModel):
    """Sagas history database table representation."""
    __tablename__ = "sagas"
    id = Column(Integer, primary_key=True)
    id_order = Column(Integer, nullable=False)
    status = Column(String(256), nullable=False)

