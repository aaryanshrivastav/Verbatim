"""Tests for order service."""

import pytest
import uuid


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_order_invalid_user(client):
    """Test creating order with invalid user."""
    response = await client.post(
        "/orders",
        json={
            "user_id": "invalid-uuid",
            "items": [],
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_order_nonexistent_user(client):
    """Test creating order with non-existent user."""
    response = await client.post(
        "/orders",
        json={
            "user_id": str(uuid.uuid4()),
            "items": [],
        },
    )
    assert response.status_code in (400, 404)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_order_not_found(client):
    """Test getting non-existent order."""
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/orders/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.unit
async def test_retry_config_endpoint(client):
    """Test retry configuration endpoint."""
    response = await client.get("/orders/retry-config")
    assert response.status_code == 200
    data = response.json()
    assert "retry_enabled" in data
    assert "max_retries" in data
