#!/usr/bin/env python3
"""
Component 1 Latency Measurement Script
Measures actual ingestion delay and end-to-end latency to prove <2s SLA
"""

import time
import requests
import json
from datetime import datetime, timezone
import statistics

class LatencyMeasurer:
    def __init__(self):
        self.results = {
            "traces": [],
            "metrics": [],
            "end_to_end": []
        }
    
    def generate_timestamped_request(self):
        """Generate a request with unique timestamp for latency measurement"""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Make request to generate telemetry
        start_time = time.time()
        response = requests.get("http://localhost:8000/", timeout=5)
        request_time = time.time() - start_time
        
        return timestamp, request_time, response.status_code
    
    def wait_for_traces(self, start_timestamp, timeout=30):
        """Wait for traces to appear in Jaeger and measure delay"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Query Jaeger for traces after our start time
                # Convert timestamp to microseconds for Jaeger API
                from datetime import datetime
                dt = datetime.fromisoformat(start_timestamp.replace('Z', '+00:00'))
                start_micros = int(dt.timestamp() * 1000000)
                
                response = requests.get(
                    f"http://localhost:16686/api/traces?service=pipeline-test&start={start_micros}&limit=5",
                    timeout=5
                )
                
                if response.status_code == 200:
                    traces = response.json().get("data", [])
                    if traces:
                        # Found traces - calculate delay
                        delay = time.time() - start_time
                        return delay, len(traces)
                
                time.sleep(0.5)  # Check every 500ms
                
            except Exception as e:
                print(f"  ⚠️  Error checking traces: {e}")
                time.sleep(1)
        
        return None, 0
    
    def wait_for_metrics(self, start_timestamp, timeout=30):
        """Wait for metrics to appear in Prometheus and measure delay"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Query Prometheus for recent metrics
                response = requests.get(
                    "http://localhost:9090/api/v1/query?query=http_request_total",
                    timeout=5
                )
                
                if response.status_code == 200:
                    data = response.json()
                    metrics = data.get("data", {}).get("result", [])
                    if metrics:
                        # Check if we have recent metrics
                        for metric in metrics:
                            value = metric.get("value", [])
                            if len(value) >= 2:
                                timestamp_ms = int(float(value[0]) * 1000)
                                
                                # Convert our timestamp to milliseconds
                                from datetime import datetime
                                dt = datetime.fromisoformat(start_timestamp.replace('Z', '+00:00'))
                                our_timestamp_ms = int(dt.timestamp() * 1000)
                                
                                # If metric timestamp is after our request timestamp
                                if timestamp_ms >= our_timestamp_ms:
                                    delay = time.time() - start_time
                                    return delay, len(metrics)
                
                time.sleep(0.5)  # Check every 500ms
                
            except Exception as e:
                print(f"  ⚠️  Error checking metrics: {e}")
                time.sleep(1)
        
        return None, 0
    
    def measure_prometheus_scrape_interval(self):
        """Measure actual Prometheus scrape interval"""
        print("🔍 Measuring Prometheus scrape interval...")
        
        try:
            # Get target info
            response = requests.get("http://localhost:9090/api/v1/targets", timeout=5)
            if response.status_code == 200:
                targets = response.json().get("data", {}).get("activeTargets", [])
                
                for target in targets:
                    if "otel-collector" in target.get("labels", {}).get("instance", ""):
                        scrape_interval = target.get("scrapeInterval", "unknown")
                        last_scrape = target.get("lastScrape", "unknown")
                        health = target.get("health", "unknown")
                        
                        print(f"  📊 OTel Collector Target:")
                        print(f"    - Scrape Interval: {scrape_interval}")
                        print(f"    - Health: {health}")
                        print(f"    - Last Scrape: {last_scrape}")
                        
                        # Verify it's 2s
                        if "2s" in scrape_interval:
                            print("  ✅ Scrape interval meets 2s SLA requirement")
                            return True
                        else:
                            print(f"  ❌ Scrape interval is {scrape_interval}, should be 2s")
                            return False
            
            print("  ❌ Could not find OTel Collector target")
            return False
            
        except Exception as e:
            print(f"  ❌ Error measuring scrape interval: {e}")
            return False
    
    def run_latency_test(self, iterations=5):
        """Run comprehensive latency test"""
        print("🚀 Component 1 Latency Measurement Test")
        print("=" * 50)
        
        # First verify Prometheus scrape interval
        scrape_ok = self.measure_prometheus_scrape_interval()
        
        print(f"\n📊 Running {iterations} latency measurements...")
        
        for i in range(iterations):
            print(f"\n🔍 Measurement {i+1}/{iterations}")
            
            # Generate timestamped request
            timestamp, request_time, status = self.generate_timestamped_request()
            print(f"  📤 Request sent at {timestamp}, took {request_time:.3f}s, status {status}")
            
            if status != 200:
                print(f"  ⚠️  Request failed with status {status}")
                continue
            
            # Measure traces delay
            print("  🔍 Waiting for traces...")
            trace_delay, trace_count = self.wait_for_traces(timestamp)
            if trace_delay:
                self.results["traces"].append(trace_delay)
                print(f"  ✅ Traces appeared after {trace_delay:.2f}s ({trace_count} traces)")
            else:
                print("  ❌ Traces not found within timeout")
                self.results["traces"].append(30)  # Max timeout
            
            # Measure metrics delay
            print("  🔍 Waiting for metrics...")
            metrics_delay, metrics_count = self.wait_for_metrics(timestamp)
            if metrics_delay:
                self.results["metrics"].append(metrics_delay)
                print(f"  ✅ Metrics appeared after {metrics_delay:.2f}s ({metrics_count} series)")
            else:
                print("  ❌ Metrics not found within timeout")
                self.results["metrics"].append(30)  # Max timeout
            
            # End-to-end latency (request + processing + visibility)
            end_to_end = request_time + (trace_delay or 30)
            self.results["end_to_end"].append(end_to_end)
            print(f"  📈 End-to-end latency: {end_to_end:.2f}s")
            
            # Wait between measurements
            if i < iterations - 1:
                print("  ⏳ Waiting 3 seconds before next measurement...")
                time.sleep(3)
    
    def analyze_results(self):
        """Analyze and report latency results"""
        print("\n" + "=" * 50)
        print("📊 LATENCY ANALYSIS RESULTS")
        print("=" * 50)
        
        def analyze_signal(name, data, sla_threshold=2.0):
            if not data:
                print(f"\n❌ {name}: No data collected")
                return False
            
            avg = statistics.mean(data)
            min_val = min(data)
            max_val = max(data)
            median = statistics.median(data)
            
            sla_met = avg < sla_threshold
            
            print(f"\n📈 {name}:")
            print(f"  Average: {avg:.2f}s")
            print(f"  Median: {median:.2f}s")
            print(f"  Min: {min_val:.2f}s")
            print(f"  Max: {max_val:.2f}s")
            print(f"  SLA (<{sla_threshold}s): {'✅ MET' if sla_met else '❌ VIOLATED'}")
            
            return sla_met
        
        # Analyze each signal
        traces_ok = analyze_signal("Traces (Jaeger)", self.results["traces"])
        metrics_ok = analyze_signal("Metrics (Prometheus)", self.results["metrics"])
        end_to_end_ok = analyze_signal("End-to-End Latency", self.results["end_to_end"])
        
        # Overall assessment
        print(f"\n🎯 OVERALL SLA ASSESSMENT:")
        print(f"  ✅ Traces: {'MEET' if traces_ok else 'VIOLATE'} <2s SLA")
        print(f"  ✅ Metrics: {'MEET' if metrics_ok else 'VIOLATE'} <2s SLA")
        print(f"  ✅ End-to-End: {'MEET' if end_to_end_ok else 'VIOLATE'} <2s SLA")
        
        overall_ok = traces_ok and metrics_ok and end_to_end_ok
        print(f"\n🎉 COMPONENT 1 SLA STATUS: {'✅ COMPLIANT' if overall_ok else '❌ NON-COMPLIANT'}")
        
        return overall_ok
    
    def save_results(self, filename="latency_results.json"):
        """Save results to file for later analysis"""
        try:
            with open(filename, 'w') as f:
                json.dump(self.results, f, indent=2)
            print(f"\n💾 Results saved to {filename}")
        except Exception as e:
            print(f"\n❌ Failed to save results: {e}")

def main():
    measurer = LatencyMeasurer()
    
    # Check if backends are accessible
    print("🔍 Checking backend accessibility...")
    backends = [
        ("Jaeger", "http://localhost:16686/api/services"),
        ("Prometheus", "http://localhost:9090/api/v1/targets"),
        ("Test Service", "http://localhost:8000/")
    ]
    
    for name, url in backends:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"  ✅ {name} accessible")
            else:
                print(f"  ❌ {name} returned {response.status_code}")
                return False
        except Exception as e:
            print(f"  ❌ {name} not accessible: {e}")
            return False
    
    print("  ✅ All backends accessible")
    
    # Run latency test
    measurer.run_latency_test(iterations=3)
    
    # Analyze results
    success = measurer.analyze_results()
    
    # Save results
    measurer.save_results()
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
