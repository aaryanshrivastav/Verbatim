"""Tests for Prometheus query construction in the detection client."""

from detection.prometheus_client import PrometheusClient


def test_p95_latency_query_uses_valid_histogram_quantile(monkeypatch):
    client = PrometheusClient("http://localhost:9090")
    captured = {}

    def fake_query(promql):
        captured["promql"] = promql
        return {
            "result": [
                {
                    "metric": {"service_name": "payment-service", "http_route": "/checkout"},
                    "value": [0, "1.25"],
                }
            ]
        }

    monkeypatch.setattr(client, "query", fake_query)

    result = client.get_p95_latency_by_service_endpoint()

    assert "sum by (le, service_name, http_route)" in captured["promql"]
    assert "histogram_quantile(0.95" in captured["promql"]
    assert result[("payment-service", "/checkout")] == 1.25


def test_request_rate_query_aggregates_by_service_and_endpoint(monkeypatch):
    client = PrometheusClient("http://localhost:9090")
    captured = {}

    def fake_query(promql):
        captured["promql"] = promql
        return {
            "result": [
                {
                    "metric": {"service_name": "gateway-service", "http_route": "/api/v1/orders"},
                    "value": [0, "3.0"],
                }
            ]
        }

    monkeypatch.setattr(client, "query", fake_query)

    result = client.get_request_rate_by_service_endpoint()

    assert captured["promql"] == (
        "sum by (service_name, http_route) "
        "(rate(http_request_total[1m]))"
    )
    assert result[("gateway-service", "/api/v1/orders")] == 3.0


def test_error_rate_queries_use_status_filter_and_aggregation(monkeypatch):
    client = PrometheusClient("http://localhost:9090")
    captured = []

    def fake_query(promql):
        captured.append(promql)
        if 'http_status_code=~"5.."' in promql:
            return {
                "result": [
                    {
                        "metric": {"service_name": "payment-service", "http_route": "/charge"},
                        "value": [0, "2.0"],
                    }
                ]
            }
        return {
            "result": [
                {
                    "metric": {"service_name": "payment-service", "http_route": "/charge"},
                    "value": [0, "10.0"],
                }
            ]
        }

    monkeypatch.setattr(client, "query", fake_query)

    result = client.get_error_rate_by_service_endpoint()

    assert captured[0] == (
        "sum by (service_name, http_route) "
        "(rate(http_request_total[1m]))"
    )
    assert captured[1] == (
        'sum by (service_name, http_route) '
        '(rate(http_request_total{http_status_code=~"5.."}[1m]))'
    )
    assert result[("payment-service", "/charge")] == 0.2
