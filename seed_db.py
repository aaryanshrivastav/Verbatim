"""Seed script to populate database with test data."""

from dotenv import load_dotenv
load_dotenv()  # Load .env file first

import asyncio
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models import Base, User, Product, Order, OrderItem, Payment
from shared.db import engine, AsyncSessionLocal


async def seed_database():
    """Seed database with test data."""
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with AsyncSessionLocal() as session:
        # Check if data already exists
        result = await session.execute(text("SELECT COUNT(*) FROM users;"))
        if result.scalar() > 0:
            print("Database already seeded, skipping...")
            return
        
        # Create test users
        user1 = User(
            id=uuid.uuid4(),
            username="john_doe",
            email="john@example.com",
        )
        user1.password = "5e884898da28047151d0e56f8dc62927538270d735b0c0487d0dcc1d82f3d4642"  # sha256("secret")
        
        user2 = User(
            id=uuid.uuid4(),
            username="jane_smith",
            email="jane@example.com",
        )
        user2.password = "5e884898da28047151d0e56f8dc62927538270d735b0c0487d0dcc1d82f3d4642"  # sha256("secret")
        
        session.add(user1)
        session.add(user2)
        await session.flush()
        
        # Create test products
        products = [
            Product(
                id=uuid.uuid4(),
                name="Laptop",
                description="High-performance laptop for engineering",
                price=Decimal("1299.99"),
                stock_quantity=50,
            ),
            Product(
                id=uuid.uuid4(),
                name="Monitor",
                description="4K UltraHD Monitor",
                price=Decimal("599.99"),
                stock_quantity=100,
            ),
            Product(
                id=uuid.uuid4(),
                name="Keyboard",
                description="Mechanical gaming keyboard",
                price=Decimal("199.99"),
                stock_quantity=200,
            ),
            Product(
                id=uuid.uuid4(),
                name="Mouse",
                description="Wireless mouse",
                price=Decimal("49.99"),
                stock_quantity=300,
            ),
            Product(
                id=uuid.uuid4(),
                name="Headphones",
                description="Noise-cancelling headphones",
                price=Decimal("349.99"),
                stock_quantity=75,
            ),
        ]
        
        for product in products:
            session.add(product)
        
        await session.flush()
        
        # Create test orders
        order1 = Order(
            id=uuid.uuid4(),
            user_id=user1.id,
            total_amount=Decimal("1849.98"),
            status="confirmed",
        )
        
        order2 = Order(
            id=uuid.uuid4(),
            user_id=user2.id,
            total_amount=Decimal("249.98"),
            status="payment_failed",
        )
        
        session.add(order1)
        session.add(order2)
        await session.flush()
        
        # Create order items
        order_items = [
            OrderItem(
                id=uuid.uuid4(),
                order_id=order1.id,
                product_id=products[0].id,  # Laptop
                quantity=1,
                unit_price=products[0].price,
            ),
            OrderItem(
                id=uuid.uuid4(),
                order_id=order1.id,
                product_id=products[1].id,  # Monitor
                quantity=1,
                unit_price=products[1].price,
            ),
            OrderItem(
                id=uuid.uuid4(),
                order_id=order2.id,
                product_id=products[2].id,  # Keyboard
                quantity=1,
                unit_price=products[2].price,
            ),
            OrderItem(
                id=uuid.uuid4(),
                order_id=order2.id,
                product_id=products[3].id,  # Mouse
                quantity=1,
                unit_price=products[3].price,
            ),
        ]
        
        for item in order_items:
            session.add(item)
        
        await session.flush()
        
        # Create payment records
        payment1 = Payment(
            id=uuid.uuid4(),
            order_id=order1.id,
            amount=order1.total_amount,
            status="completed",
            payment_method="credit_card",
            transaction_id=f"txn_{order1.id.hex[:12]}",
        )
        
        payment2 = Payment(
            id=uuid.uuid4(),
            order_id=order2.id,
            amount=order2.total_amount,
            status="failed",
            payment_method="credit_card",
            transaction_id=None,
        )
        
        session.add(payment1)
        session.add(payment2)
        
        # Commit all changes
        await session.commit()
        
        print("✓ Database seeded successfully!")
        print(f"  - Created 2 users")
        print(f"  - Created 5 products")
        print(f"  - Created 2 orders with 4 items")
        print(f"  - Created 2 payment records")


if __name__ == "__main__":
    asyncio.run(seed_database())
