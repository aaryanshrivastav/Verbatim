"""Tests for auth service."""

import pytest


@pytest.mark.asyncio
@pytest.mark.unit
async def test_validate_auth_no_credentials(client):
    """Test validation fails with no credentials."""
    response = await client.post("/auth/validate", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_login_missing_credentials(client):
    """Test login fails with missing username or password."""
    response = await client.post("/auth/login", json={"username": "test"})
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_health_includes_database(client):
    """Test auth health endpoint checks database."""
    response = await client.get("/health")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "checks" in data
