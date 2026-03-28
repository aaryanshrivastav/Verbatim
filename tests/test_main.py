"""Tests for main application endpoints."""

import pytest


@pytest.mark.asyncio
async def test_root_endpoint(client):
    """Test root endpoint returns documentation links."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Microservices Observability Demo"
    assert "docs" in data
    assert "services" in data


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Test health check endpoint."""
    response = await client.get("/health")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "healthy" in data
    assert "checks" in data


@pytest.mark.asyncio
async def test_metrics_endpoint(client):
    """Test metrics endpoint returns Prometheus format."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    # Prometheus format is plain text
    assert "http_request_total" in response.text or response.text


@pytest.mark.asyncio
async def test_readiness_endpoint(client):
    """Test readiness probe endpoint."""
    response = await client.get("/readiness")
    assert response.status_code in (200, 503)
    data = response.json()
    assert "ready" in data


@pytest.mark.asyncio
async def test_liveness_endpoint(client):
    """Test liveness probe endpoint."""
    response = await client.get("/liveness")
    assert response.status_code == 200
    data = response.json()
    assert data["alive"] is True
