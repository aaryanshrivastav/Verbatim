#!/bin/bash

# Component 1 Setup Script
# Run this to set up the complete observability pipeline

echo "🚀 Setting up Component 1 Observability Pipeline..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is required but not installed."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is required but not installed."
    exit 1
fi

echo "✅ Prerequisites check passed"

# Create virtual environment
echo "📦 Creating Python virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "📚 Installing Python requirements..."
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    cat > .env << EOF
# Database Configuration
DATABASE_URL=postgresql+asyncpg://user:password@localhost/microservices_db

# Redis Configuration  
REDIS_URL=redis://localhost:6379/0

# OpenTelemetry Configuration
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Service URLs
AUTH_URL=http://localhost:8001
CATALOG_URL=http://localhost:8002
ORDER_URL=http://localhost:8003
PAYMENT_URL=http://localhost:8004

# Retry Configuration
ENABLE_RETRY_STORMS=false
MAX_RETRIES=3
RETRY_BACKOFF_FACTOR=2
RETRY_JITTER=true

# HTTP Configuration
HTTP_TIMEOUT_SECONDS=30

# Cache Configuration
CACHE_TTL_SECONDS=300

# Database Configuration
DB_POOL_SIZE=20

# Payment Simulation
PAYMENT_SUCCESS_RATE=0.8
PAYMENT_TIMEOUT_RATE=0.1
PAYMENT_ERROR_RATE=0.1
EOF
fi

echo "✅ Setup complete!"
echo ""
echo "🎯 Next steps:"
echo "1. Activate virtual environment: source venv/bin/activate"
echo "2. Start observability stack: cd observability && docker-compose up -d"
echo "3. Run the test: python test_complete_pipeline.py"
echo "4. Open UIs:"
echo "   - Jaeger: http://localhost:16686"
echo "   - Prometheus: http://localhost:9090"
echo "   - Grafana: http://localhost:3000"
