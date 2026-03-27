"""Tests for catalog service."""

import pytest


@pytest.mark.asyncio
@pytest.mark.unit
async def test_list_products_empty(client):
    """Test listing products when none exist."""
    response = await client.get("/products")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_product_not_found(client):
    """Test getting non-existent product."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"/products/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_product_invalid_id_format(client):
    """Test getting product with invalid UUID format."""
    response = await client.get("/products/invalid-id")
    assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cache_status_endpoint(client):
    """Test cache status endpoint."""
    response = await client.get("/products/cache-status/test-key")
    assert response.status_code == 200
    data = response.json()
    assert "key" in data
    assert "exists" in data
