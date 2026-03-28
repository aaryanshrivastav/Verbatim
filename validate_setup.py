#!/usr/bin/env python3
"""
Setup Validation Script
Validates that the complete Component 1 pipeline is working correctly
"""

import subprocess
import requests
import time
import sys

def run_command(cmd, description):
    """Run a command and return success status"""
    print(f"🔍 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"✅ {description} - SUCCESS")
            return True
        else:
            print(f"❌ {description} - FAILED")
            print(f"   Error: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print(f"❌ {description} - TIMEOUT")
        return False
    except Exception as e:
        print(f"❌ {description} - ERROR: {e}")
        return False

def check_url(url, description):
    """Check if a URL is accessible"""
    print(f"🔍 Checking {description}...")
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            print(f"✅ {description} - ACCESSIBLE")
            return True
        else:
            print(f"❌ {description} - HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ {description} - ERROR: {e}")
        return False

def main():
    print("🧪 COMPONENT 1 SETUP VALIDATION")
    print("=" * 50)
    
    results = []
    
    # Check prerequisites
    print("\n📋 CHECKING PREREQUISITES...")
    results.append(run_command("python --version", "Python installation"))
    results.append(run_command("docker --version", "Docker installation"))
    results.append(run_command("docker-compose --version", "Docker Compose installation"))
    
    # Check Docker services
    print("\n🐳 CHECKING DOCKER SERVICES...")
    results.append(run_command("cd observability && docker-compose ps", "Docker Compose services"))
    
    # Check backend connectivity
    print("\n🌐 CHECKING BACKEND CONNECTIVITY...")
    results.append(check_url("http://localhost:16686/api/services", "Jaeger API"))
    results.append(check_url("http://localhost:9090/api/v1/targets", "Prometheus API"))
    results.append(check_url("http://localhost:3100/ready", "Loki readiness"))
    results.append(check_url("http://localhost:8889/metrics", "OTel Collector metrics"))
    
    # Check Grafana
    results.append(check_url("http://localhost:3000/api/health", "Grafana health"))
    
    # Validate Python dependencies
    print("\n🐍 CHECKING PYTHON DEPENDENCIES...")
    try:
        import opentelemetry.instrumentation.fastapi
        import opentelemetry.instrumentation.sqlalchemy
        import opentelemetry.instrumentation.httpx
        import opentelemetry.instrumentation.redis
        print("✅ OpenTelemetry instrumentation packages - INSTALLED")
        results.append(True)
    except ImportError as e:
        print(f"❌ OpenTelemetry instrumentation packages - MISSING: {e}")
        results.append(False)
    
    # Check if test can run
    print("\n🧪 CHECKING PIPELINE TEST...")
    try:
        # Try to import the test modules
        import test_complete_pipeline
        print("✅ Pipeline test imports - SUCCESS")
        results.append(True)
    except ImportError as e:
        print(f"❌ Pipeline test imports - FAILED: {e}")
        results.append(False)
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 VALIDATION RESULTS")
    print("=" * 50)
    
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"🎉 ALL CHECKS PASSED ({passed}/{total})")
        print("\n✅ Component 1 is ready for demonstration!")
        print("\n🎯 Next steps:")
        print("1. Run the pipeline test: python test_complete_pipeline.py")
        print("2. Open the UIs:")
        print("   - Jaeger: http://localhost:16686")
        print("   - Prometheus: http://localhost:9090")
        print("   - Grafana: http://localhost:3000")
        print("3. Generate traffic and watch telemetry appear!")
        return True
    else:
        print(f"❌ SOME CHECKS FAILED ({passed}/{total})")
        print("\n🔧 Fix issues before running demonstration:")
        
        if not results[0]: print("- Install Python 3.8+")
        if not results[1]: print("- Install Docker")
        if not results[2]: print("- Install Docker Compose")
        if not results[3]: print("- Start observability stack: cd observability && docker-compose up -d")
        if not results[4]: print("- Check Jaeger is running on port 16686")
        if not results[5]: print("- Check Prometheus is running on port 9090")
        if not results[6]: print("- Check Loki is running on port 3100")
        if not results[7]: print("- Check OTel Collector is running on port 8889")
        if not results[8]: print("- Check Grafana is running on port 3000")
        if not results[9]: print("- Install requirements: pip install -r requirements.txt")
        if not results[10]: print("- Fix import errors in test modules")
        
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
