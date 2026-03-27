"""Tests for payment service."""

import pytest
import uuid


@pytest.mark.asyncio
@pytest.mark.unit
async def test_charge_invalid_order_id(client):
    """Test charge with invalid order ID."""
    response = await client.post(
        "/charge",
        json={
            "order_id": "invalid-uuid",
            "amount": "99.99",
            "currency": "USD",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.unit
async def test_simulate_failure_toggle_timeout(client):
    """Test toggling timeout simulation."""
    response = await client.post(
        "/charge/simulate-failure",
        json={"always_timeout": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"]["always_timeout"] is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_simulate_failure_toggle_fail(client):
    """Test toggling failure simulation."""
    response = await client.post(
        "/charge/simulate-failure",
        json={"always_fail": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"]["always_fail"] is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_simulate_failure_toggle_normal(client):
    """Test returning to normal simulation."""
    response = await client.post(
        "/charge/simulate-failure",
        json={"normal": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["state"]["normal"] is True
