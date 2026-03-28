"""Conftest: Shared pytest fixtures for data_collection tests."""

import pytest
import logging

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def disable_logs(caplog):
    """Fixture to suppress logs during tests."""
    caplog.set_level(logging.CRITICAL)
    return caplog
