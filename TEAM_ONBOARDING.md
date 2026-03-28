# Team Onboarding Guide - Component 1

## 🎯 What We Built

**Component 1: Complete Observability Pipeline** - A production-ready telemetry system that gets logs, metrics, and traces queryable in <2s with consistent service identity.

### Architecture
```
Services (OTel SDK) → OTel Collector → {Jaeger, Prometheus, Loki}
```

### Key Features
- ✅ **<2s queryability** (Prometheus 2s scrape interval)
- ✅ **Consistent service identity** across all signals
- ✅ **Signal priorities**: Traces (primary), Metrics (secondary), Logs (tertiary)
- ✅ **No cross-signal linking** (correlation by service+time only)
- ✅ **Production sampling** (10% for scalability)

## 🚀 Quick Start for Team Members

### Prerequisites
- Python 3.8+
- Docker & Docker Compose
- Git

### One-Command Setup
```bash
git clone <repository>
cd <repository>

# Linux/Mac
./setup.sh

# Windows
.\setup.ps1
```

### Manual Setup (if setup script fails)
```bash
# 1. Virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\Activate.ps1  # Windows

# 2. Dependencies (pkg_resources issues fixed!)
pip install -r requirements.txt

# 3. Environment
cp .env.example .env

# 4. Start observability stack
cd observability
docker-compose up -d

# 5. Run test
cd ..
python test_complete_pipeline.py
```

## 🔍 Verification Steps

### 1. Check All Services Running
```bash
cd observability
docker-compose ps
```

### 2. Access UIs
- **Jaeger**: http://localhost:16686 (should show "pipeline-test" service)
- **Prometheus**: http://localhost:9090 (should show 2s scrape interval)
- **Grafana**: http://localhost:3000 (admin/admin)
- **Loki**: http://localhost:3100/ready

### 3. Run Pipeline Test
```bash
python test_complete_pipeline.py
```

Expected output:
- ✅ All backends accessible
- ✅ Traces found in Jaeger
- ✅ Metrics working
- ✅ Logs working

## 🐛 Common Issues & Fixes

### pkg_resources Error
**Problem**: `ModuleNotFoundError: No module named 'pkg_resources'`
**Solution**: Use our fixed requirements.txt - we pinned setuptools==68.0.0

### Loki Ring Health Error
**Problem**: "too many unhealthy instances in the ring"
**Solution**: Restart Loki - `docker-compose restart loki`

### OTel Collector Configuration Error
**Problem**: "unknown type: jaeger/loki exporter"
**Solution**: We're using otel-collector-contrib:0.88.0 with correct exporter names

### Port Conflicts
**Problem**: Ports already in use
**Solution**: Check what's using ports 8000, 4317, 16686, 9090, 3000, 3100

## 📊 What to Demonstrate

### 1. Real-Time Telemetry Flow
```bash
# Start the test
python test_complete_pipeline.py

# Watch in real-time:
# - Jaeger: Traces appear instantly
# - Prometheus: Metrics update every 2s
# - Console: Structured JSON logs
```

### 2. Signal Priorities
- **Traces**: Click any trace in Jaeger → see complete request journey
- **Metrics**: In Prometheus, run `rate(http_request_total[2m])` → see request rate
- **Logs**: In console, see `{"service": "pipeline-test", ...}` structured logs

### 3. SLA Compliance
- **<2s queryability**: Prometheus shows 2s scrape interval
- **Service identity**: Same service name in traces, metrics, logs
- **Signal separation**: No trace_id in logs (by design)

## 🎯 Key Talking Points

### For Management
- "We achieved <2s queryability meeting our SLA requirements"
- "Consistent service identity enables accurate correlation"
- "Signal prioritization ensures critical path performance"

### For Technical Team
- "Auto-instrumentation eliminates manual tracing code"
- "10% sampling makes this production-ready at scale"
- "Stateless collector design supports horizontal scaling"

### For Demo
- "Watch traces appear in real-time as we generate traffic"
- "See how metrics update every 2s in Prometheus"
- "Notice the consistent service identity across all three signals"

## 🔧 Development Workflow

### Making Changes
1. Update code
2. Run `python test_complete_pipeline.py` to verify
3. Check UIs to confirm changes work
4. Commit and push

### Adding New Services
1. Copy existing service structure
2. Add OpenTelemetry instrumentation
3. Update service name in setup_opentelemetry()
4. Add to docker-compose if needed

### Debugging Issues
1. Check logs: `cd observability && docker-compose logs <service>`
2. Verify connectivity: `curl http://localhost:<port>/health`
3. Run validation: `python validate_component1.py`

## 📱 Mobile/Tablet Access

For demos on mobile devices, use your machine's IP:
- Jaeger: http://YOUR_IP:16686
- Prometheus: http://YOUR_IP:9090
- Grafana: http://YOUR_IP:3000

## 🚀 Production Considerations

### Scaling
- OTel Collector: Deploy multiple instances behind load balancer
- Sampling: Adjust based on traffic (1-10% typical)
- Storage: Consider managed Prometheus/Jaeger services

### Security
- Add authentication to UIs
- Use HTTPS in production
- Secure OTLP endpoints

### Monitoring
- Monitor the monitoring system!
- Set up alerts for pipeline health
- Track ingestion latency

---

## 🆘 Get Help

If you encounter issues:

1. **Check this document first** - most solutions are here
2. **Run the validation script**: `python validate_component1.py`
3. **Check logs**: `cd observability && docker-compose logs`
4. **Ask the team**: Share error logs and what you've tried

---

**Remember**: This is Component 1 of a complete observability system. It's production-ready and demonstrates all core requirements!
