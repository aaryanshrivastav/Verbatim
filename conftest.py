"""Pytest configuration and fixtures."""

from dotenv import load_dotenv
load_dotenv()  # Load .env file first, before any config imports

import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from models import Base
from shared.config import DATABASE_URL


# Override database for tests
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    future=True,
    poolclass=StaticPool,  # Use StaticPool for in-memory SQLite (ensures all connections use same database)
)

TestAsyncSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False, future=True
)


@pytest.fixture(scope="session")
def event_loop():
    """Create session-scoped event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Set up test database and create tables."""
    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    # Drop tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await test_engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def setup_test_dependencies():
    """Set up all test dependencies: mock Redis and test database."""
    from shared.redis_client import get_redis_client
    from shared.db import get_db_session
    
    # Mock Redis
    class MockRedis:
        def __init__(self):
            self._data = {}

        async def get(self, key: str):
            return self._data.get(key)

        async def set(self, key: str, value: str):
            self._data[key] = value
            return True

        async def setex(self, key: str, ttl: int, value: str):
            self._data[key] = value
            return True

        async def delete(self, key: str):
            self._data.pop(key, None)
            return True

        async def exists(self, key: str):
            return key in self._data

        async def ttl(self, key: str):
            return -1  # No expiration

        async def ping(self):
            return True

        async def close(self):
            pass

    mock_redis_instance = MockRedis()
    
    # Override Redis
    async def override_redis():
        return mock_redis_instance
    
    # Override Database
    async def override_db():
        async with TestAsyncSessionLocal() as session:
            yield session
    
    app.dependency_overrides[get_redis_client] = override_redis
    app.dependency_overrides[get_db_session] = override_db
    
    yield
    
    # Cleanup
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a test database session."""
    async with TestAsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client for testing the API."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_user_data():
    """Sample user data for testing."""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword123",
    }


@pytest.fixture
def sample_product_data():
    """Sample product data for testing."""
    return {
        "name": "Test Product",
        "description": "A test product",
        "price": "99.99",
        "stock_quantity": 100,
    }


@pytest.fixture
def sample_order_data():
    """Sample order data for testing."""
    import uuid
    
    return {
        "user_id": str(uuid.uuid4()),
        "items": [
            {
                "product_id": str(uuid.uuid4()),
                "quantity": 2,
            }
        ],
    }


@pytest.fixture
def sample_payment_data():
    """Sample payment data for testing."""
    import uuid
    
    return {
        "order_id": str(uuid.uuid4()),
        "amount": "199.99",
        "currency": "USD",
    }
