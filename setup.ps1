# Component 1 Setup Script for Windows
# Run this to set up the complete observability pipeline

Write-Host "🚀 Setting up Component 1 Observability Pipeline..."

# Check if Python is installed
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python found: $pythonVersion"
} catch {
    Write-Host "❌ Python is required but not installed."
    exit 1
}

# Check if Docker is installed
try {
    $dockerVersion = docker --version 2>&1
    Write-Host "✅ Docker found: $dockerVersion"
} catch {
    Write-Host "❌ Docker is required but not installed."
    exit 1
}

# Check if Docker Compose is installed
try {
    $composeVersion = docker-compose --version 2>&1
    Write-Host "✅ Docker Compose found: $composeVersion"
} catch {
    Write-Host "❌ Docker Compose is required but not installed."
    exit 1
}

Write-Host "✅ Prerequisites check passed"

# Create virtual environment
Write-Host "📦 Creating Python virtual environment..."
python -m venv venv

# Activate virtual environment
Write-Host "🔧 Activating virtual environment..."
.\venv\Scripts\Activate.ps1

# Upgrade pip
Write-Host "⬆️  Upgrading pip..."
python -m pip install --upgrade pip

# Install requirements
Write-Host "📚 Installing Python requirements..."
pip install -r requirements.txt

# Create .env file if it doesn't exist
if (-not (Test-Path .env)) {
    Write-Host "📝 Creating .env file..."
    @"
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
"@ | Out-File -FilePath .env -Encoding utf8
}

Write-Host "✅ Setup complete!"
Write-Host ""
Write-Host "🎯 Next steps:"
Write-Host "1. Activate virtual environment: .\venv\Scripts\Activate.ps1"
Write-Host "2. Start observability stack: cd observability; docker-compose up -d"
Write-Host "3. Run the test: python test_complete_pipeline.py"
Write-Host "4. Open UIs:"
Write-Host "   - Jaeger: http://localhost:16686"
Write-Host "   - Prometheus: http://localhost:9090"
Write-Host "   - Grafana: http://localhost:3000"
