"""
SQLAlchemy ORM models for Kubernetes observability microservices demo.
Defines PostgreSQL tables with UUID primary keys and timezone-aware timestamps.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Boolean,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

# Toggle to enable/disable sessions table
ENABLE_SESSIONS = True

Base = declarative_base()


class User(Base):
    """User account information."""

    __tablename__ = "users"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")
    if ENABLE_SESSIONS:
        sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"


if ENABLE_SESSIONS:

    class Session(Base):
        """User session tokens with expiration."""

        __tablename__ = "sessions"

        id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
        user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
        token = Column(String(512), unique=True, nullable=False, index=True)
        expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
        created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

        # Relationships
        user = relationship("User", back_populates="sessions")

        def __repr__(self):
            return f"<Session(id={self.id}, user_id={self.user_id})>"


class Product(Base):
    """Product catalog information."""

    __tablename__ = "products"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    price = Column(Numeric(precision=10, scale=2), nullable=False)
    stock_quantity = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    order_items = relationship("OrderItem", back_populates="product")

    def __repr__(self):
        return f"<Product(id={self.id}, name='{self.name}', price={self.price})>"


class Order(Base):
    """Customer orders."""

    __tablename__ = "orders"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    total_amount = Column(Numeric(precision=12, scale=2), nullable=False)
    status = Column(String(50), nullable=False, default="pending", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    user = relationship("User", back_populates="orders")
    order_items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="order", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Order(id={self.id}, user_id={self.user_id}, status='{self.status}')>"


class OrderItem(Base):
    """Individual items within an order."""

    __tablename__ = "order_items"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(Uuid(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(Uuid(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(precision=10, scale=2), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    order = relationship("Order", back_populates="order_items")
    product = relationship("Product", back_populates="order_items")

    def __repr__(self):
        return f"<OrderItem(id={self.id}, order_id={self.order_id}, product_id={self.product_id})>"


class Payment(Base):
    """Payment records for orders."""

    __tablename__ = "payments"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(Uuid(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True)
    amount = Column(Numeric(precision=12, scale=2), nullable=False)
    status = Column(String(50), nullable=False, default="pending", index=True)
    payment_method = Column(String(100), nullable=False)
    transaction_id = Column(String(255), unique=True, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    order = relationship("Order", back_populates="payments")

    def __repr__(self):
        return f"<Payment(id={self.id}, order_id={self.order_id}, status='{self.status}')>"


class CacheInvalidationLog(Base):
    """Audit log for cache invalidation events."""

    __tablename__ = "cache_invalidation_log"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String(100), nullable=False, index=True)
    entity_id = Column(Uuid(as_uuid=True), nullable=False, index=True)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "created_at", name="uix_entity_invalidation"),)

    def __repr__(self):
        return f"<CacheInvalidationLog(id={self.id}, entity_type='{self.entity_type}', entity_id={self.entity_id})>"
