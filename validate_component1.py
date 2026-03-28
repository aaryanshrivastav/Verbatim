#!/usr/bin/env python3
"""
Component 1 Validation Script
Validates all critical requirements and measures actual performance
"""

import asyncio
import time
import requests
import json
from datetime import datetime, timedelta

class Component1Validator:
    def __init__(self):
        self.results = {
            "traces_working": False,
            "metrics_working": False, 
            "logs_working": False,
            "prometheus_scrape_interval": None,
            "actual_ingestion_delay": None,
            "service_identity_consistent": False,
            "sampling_rate": None,
            "end_to_end_latency": {}
        }
    
    def test_traces_pipeline(self):
        """Test traces: Services → OTel Collector → Jaeger"""
        print("🔍 Testing Traces Pipeline...")
        
        try:
            # Check Jaeger services
            response = requests.get("http://localhost:16686/api/services", timeout=5)
            if response.status_code == 200:
                services = response.json().get("data", [])
                if len(services) > 0:
                    print(f"  ✅ Jaeger has {len(services)} services: {services}")
                    
                    # Check for our test service
                    if "pipeline-test" in services:
                        print("  ✅ Test service traces found in Jaeger")
                        
                        # Get trace details
                        trace_response = requests.get(
                            "http://localhost:16686/api/traces?service=pipeline-test&limit=5", 
                            timeout=5
                        )
                        if trace_response.status_code == 200:
                            traces = trace_response.json().get("data", [])
                            if len(traces) > 0:
                                print(f"  ✅ Found {len(traces)} traces with detailed spans")
                                self.results["traces_working"] = True
                            else:
                                print("  ⚠️  No traces found for test service")
                        else:
                            print("  ❌ Failed to get trace details")
                    else:
                        print("  ⚠️  Test service not found in Jaeger")
                else:
                    print("  ❌ No services found in Jaeger")
            else:
                print("  ❌ Jaeger API not accessible")
                
        except Exception as e:
            print(f"  ❌ Traces test failed: {e}")
    
    def test_metrics_pipeline(self):
        """Test metrics: Services → OTel Collector → Prometheus"""
        print("🔍 Testing Metrics Pipeline...")
        
        try:
            # Check Prometheus targets
            response = requests.get("http://localhost:9090/api/v1/targets", timeout=5)
            if response.status_code == 200:
                targets = response.json().get("data", {}).get("activeTargets", [])
                
                otel_collector_target = None
                for target in targets:
                    if "otel-collector:8889" in target.get("labels", {}).get("instance", ""):
                        otel_collector_target = target
                        break
                
                if otel_collector_target:
                    health = otel_collector_target.get("health", "unknown")
                    last_scrape = otel_collector_target.get("lastScrape", "unknown")
                    scrape_interval = otel_collector_target.get("scrapeInterval", "unknown")
                    
                    print(f"  ✅ OTel Collector target: health={health}, scrape={scrape_interval}")
                    
                    # Validate scrape interval is 2s
                    if "2s" in scrape_interval:
                        print("  ✅ Prometheus scrape interval is correctly set to 2s")
                        self.results["prometheus_scrape_interval"] = "2s"
                    else:
                        print(f"  ❌ Scrape interval is {scrape_interval}, should be 2s")
                    
                    # Check for actual metrics
                    metrics_response = requests.get(
                        "http://localhost:9090/api/v1/query?query=up", 
                        timeout=5
                    )
                    if metrics_response.status_code == 200:
                        metrics = metrics_response.json().get("data", {}).get("result", [])
                        if len(metrics) > 0:
                            print(f"  ✅ Prometheus has {len(metrics)} metrics series")
                            self.results["metrics_working"] = True
                        else:
                            print("  ❌ No metrics found in Prometheus")
                    else:
                        print("  ❌ Failed to query Prometheus metrics")
                else:
                    print("  ❌ OTel Collector target not found in Prometheus")
            else:
                print("  ❌ Prometheus API not accessible")
                
        except Exception as e:
            print(f"  ❌ Metrics test failed: {e}")
    
    def test_logs_pipeline(self):
        """Test logs: Services → OTel Collector → Loki"""
        print("🔍 Testing Logs Pipeline...")
        
        try:
            # Check Loki readiness
            response = requests.get("http://localhost:3100/ready", timeout=5)
            if response.status_code == 200:
                print("  ✅ Loki is ready")
                
                # Query for our test service logs
                # URL encoded query: {service="pipeline-test"}
                query_response = requests.get(
                    "http://localhost:3100/loki/api/v1/query?query=%7Bservice%3D%22pipeline-test%22%7D",
                    timeout=5
                )
                
                if query_response.status_code == 200:
                    logs_data = query_response.json()
                    result = logs_data.get("data", {}).get("result", [])
                    
                    if len(result) > 0:
                        print(f"  ✅ Found {len(result)} log entries for test service")
                        self.results["logs_working"] = True
                    else:
                        print("  ⚠️  No logs found for test service (may need more time)")
                else:
                    print(f"  ❌ Loki query failed: {query_response.status_code}")
            else:
                print("  ❌ Loki not ready")
                
        except Exception as e:
            print(f"  ❌ Logs test failed: {e}")
    
    def test_service_identity_consistency(self):
        """Test consistent service identity across signals"""
        print("🔍 Testing Service Identity Consistency...")
        
        try:
            # Check traces for service name
            trace_response = requests.get(
                "http://localhost:16686/api/traces?service=pipeline-test&limit=1", 
                timeout=5
            )
            
            if trace_response.status_code == 200:
                traces = trace_response.json().get("data", [])
                if len(traces) > 0:
                    trace_service = traces[0].get("processes", {}).get("p1", {}).get("serviceName", "")
                    if trace_service == "pipeline-test":
                        print("  ✅ Service name consistent in traces")
                        
                        # Check metrics for service labels
                        metrics_response = requests.get(
                            "http://localhost:8889/metrics", 
                            timeout=5
                        )
                        
                        if metrics_response.status_code == 200:
                            if "pipeline-test" in metrics_response.text:
                                print("  ✅ Service name consistent in metrics")
                                self.results["service_identity_consistent"] = True
                            else:
                                print("  ⚠️  Service name not found in metrics")
                        else:
                            print("  ❌ Failed to check OTel Collector metrics")
                    else:
                        print(f"  ❌ Service name mismatch in traces: {trace_service}")
                else:
                    print("  ❌ No traces found to check service identity")
            else:
                print("  ❌ Failed to get traces for identity check")
                
        except Exception as e:
            print(f"  ❌ Service identity test failed: {e}")
    
    def measure_ingestion_delay(self):
        """Measure actual ingestion delay"""
        print("🔍 Measuring Ingestion Delay...")
        
        try:
            # Generate a timestamped request
            start_time = time.time()
            timestamp = datetime.utcnow().isoformat()
            
            # Make a request to generate telemetry
            response = requests.get("http://localhost:8000/", timeout=5)
            
            if response.status_code == 200:
                print("  ✅ Test request sent")
                
                # Wait and check when data appears in backends
                delay_times = {}
                
                # Check traces delay
                for i in range(10):  # Wait up to 10 seconds
                    time.sleep(1)
                    trace_response = requests.get(
                        f"http://localhost:16686/api/traces?service=pipeline-test&start={int(start_time*1000000)}",
                        timeout=5
                    )
                    if trace_response.status_code == 200:
                        traces = trace_response.json().get("data", [])
                        if len(traces) > 0:
                            delay_times["traces"] = time.time() - start_time
                            print(f"  ✅ Traces appeared after {delay_times['traces']:.2f}s")
                            break
                
                # Check metrics delay
                for i in range(10):  # Wait up to 10 seconds
                    time.sleep(1)
                    metrics_response = requests.get(
                        "http://localhost:9090/api/v1/query?query=http_request_total",
                        timeout=5
                    )
                    if metrics_response.status_code == 200:
                        metrics = metrics_response.json().get("data", {}).get("result", [])
                        if len(metrics) > 0:
                            delay_times["metrics"] = time.time() - start_time
                            print(f"  ✅ Metrics appeared after {delay_times['metrics']:.2f}s")
                            break
                
                self.results["actual_ingestion_delay"] = delay_times
                
                # Check if within 2s SLA
                max_delay = max(delay_times.values()) if delay_times else 999
                if max_delay < 2.0:
                    print(f"  ✅ Ingestion delay {max_delay:.2f}s meets <2s SLA")
                else:
                    print(f"  ❌ Ingestion delay {max_delay:.2f}s exceeds 2s SLA")
            else:
                print("  ❌ Test request failed")
                
        except Exception as e:
            print(f"  ❌ Ingestion delay measurement failed: {e}")
    
    def test_sampling_configuration(self):
        """Check trace sampling rate"""
        print("🔍 Checking Trace Sampling...")
        
        try:
            # This would require checking the actual SDK configuration
            # For now, we'll note that we're using default (likely 100% sampling)
            print("  ⚠️  Using default OpenTelemetry sampling (likely 100%)")
            print("  💡 Recommendation: Configure sampling for production:")
            print("     - ParentBased(root: TraceIdRatioBased(0.01)) for 1% sampling")
            self.results["sampling_rate"] = "100% (default)"
            
        except Exception as e:
            print(f"  ❌ Sampling check failed: {e}")
    
    def generate_report(self):
        """Generate comprehensive validation report"""
        print("\n" + "="*80)
        print("📊 COMPONENT 1 VALIDATION REPORT")
        print("="*80)
        
        print("\n🎯 SIGNAL PIPELINES:")
        print(f"  ✅ Traces: {'WORKING' if self.results['traces_working'] else 'BROKEN'}")
        print(f"  ✅ Metrics: {'WORKING' if self.results['metrics_working'] else 'BROKEN'}")
        print(f"  ✅ Logs: {'WORKING' if self.results['logs_working'] else 'BROKEN'}")
        
        print("\n⚡ PERFORMANCE:")
        print(f"  📈 Prometheus Scrape Interval: {self.results['prometheus_scrape_interval']}")
        if self.results['actual_ingestion_delay']:
            for signal, delay in self.results['actual_ingestion_delay'].items():
                status = "✅" if delay < 2.0 else "❌"
                print(f"  {status} {signal.title()} Delay: {delay:.2f}s")
        
        print("\n🔧 CONFIGURATION:")
        print(f"  🏷️  Service Identity: {'CONSISTENT' if self.results['service_identity_consistent'] else 'INCONSISTENT'}")
        print(f"  📊 Sampling Rate: {self.results['sampling_rate']}")
        
        print("\n🚨 CRITICAL ISSUES:")
        issues = []
        
        if not self.results['traces_working']:
            issues.append("❌ Traces pipeline broken - RCA will fail")
        if not self.results['metrics_working']:
            issues.append("❌ Metrics pipeline broken - anomaly detection disabled")
        if not self.results['logs_working']:
            issues.append("❌ Logs pipeline broken - evidence collection disabled")
        if self.results['prometheus_scrape_interval'] != "2s":
            issues.append("❌ Prometheus scrape interval not 2s - SLA violation")
        if not self.results['service_identity_consistent']:
            issues.append("❌ Service identity inconsistent - correlation broken")
        if self.results['sampling_rate'] == "100% (default)":
            issues.append("⚠️  100% sampling - not scalable for production")
        
        if issues:
            for issue in issues:
                print(f"  {issue}")
        else:
            print("  ✅ No critical issues found")
        
        print("\n📋 RECOMMENDATIONS:")
        if self.results['sampling_rate'] == "100% (default)":
            print("  🔧 Configure trace sampling (1-10% for production)")
        print("  🔧 Add latency monitoring and alerting")
        print("  🔧 Implement circuit breakers for backend failures")
        print("  🔧 Add comprehensive health checks")
        
        # Overall status
        all_working = all([
            self.results['traces_working'],
            self.results['metrics_working'], 
            self.results['logs_working'],
            self.results['prometheus_scrape_interval'] == "2s",
            self.results['service_identity_consistent']
        ])
        
        print(f"\n🎉 OVERALL STATUS: {'PRODUCTION READY' if all_working else 'NEEDS FIXES'}")
        
        return all_working

def main():
    validator = Component1Validator()
    
    print("🧪 COMPONENT 1 COMPREHENSIVE VALIDATION")
    print("="*50)
    
    # Run all tests
    validator.test_traces_pipeline()
    validator.test_metrics_pipeline()
    validator.test_logs_pipeline()
    validator.test_service_identity_consistency()
    validator.measure_ingestion_delay()
    validator.test_sampling_configuration()
    
    # Generate report
    is_ready = validator.generate_report()
    
    return is_ready

if __name__ == "__main__":
    success = main()
    input("\nPress Enter to exit...")
    exit(0 if success else 1)
