"""Configuration and environment variables."""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost/microservices_db")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_CACHE_TTL = int(os.getenv("REDIS_CACHE_TTL", "3600"))

# Services (for inter-service calls)
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")
CATALOG_SERVICE_URL = os.getenv("CATALOG_SERVICE_URL", "http://localhost:8002")
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://localhost:8003")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://localhost:8004")

# Retry settings
ENABLE_RETRY_STORM = os.getenv("ENABLE_RETRY_STORM", "false").lower() == "true"
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
INITIAL_BACKOFF_SECONDS = float(os.getenv("INITIAL_BACKOFF_SECONDS", "1"))
MAX_BACKOFF_SECONDS = float(os.getenv("MAX_BACKOFF_SECONDS", "32"))

# Timeouts
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))

# Payment simulation
PAYMENT_SUCCESS_RATE = float(os.getenv("PAYMENT_SUCCESS_RATE", "0.99"))  # 99% success for baseline
PAYMENT_TIMEOUT_RATE = float(os.getenv("PAYMENT_TIMEOUT_RATE", "0.0"))  # 0% timeout for baseline
