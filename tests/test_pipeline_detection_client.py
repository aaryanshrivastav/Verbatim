from pipeline_integration.detection_client import DetectionApiClient


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_detection_api_client_refreshes_config(monkeypatch):
    calls = []

    def fake_get(url, timeout):
        calls.append((url, timeout))
        return _Response(
            {
                "status": "ok",
                "config": {
                    "poll_interval_seconds": 3,
                },
            }
        )

    monkeypatch.setattr("pipeline_integration.detection_client.requests.get", fake_get)

    client = DetectionApiClient("http://localhost:8010", timeout_seconds=7)

    assert calls == [("http://localhost:8010/status", 7)]
    assert client.config.poll_interval_seconds == 3


def test_detection_api_client_tick_posts_to_remote_service(monkeypatch):
    monkeypatch.setattr(
        "pipeline_integration.detection_client.requests.get",
        lambda url, timeout: _Response({"status": "ok", "config": {"poll_interval_seconds": 1}}),
    )
    posted = []

    def fake_post(url, timeout):
        posted.append((url, timeout))
        return _Response({"events": [], "incidents": [], "in_warmup": False})

    monkeypatch.setattr("pipeline_integration.detection_client.requests.post", fake_post)

    client = DetectionApiClient("http://localhost:8010", timeout_seconds=5)
    payload = client.tick()

    assert posted == [("http://localhost:8010/tick", 5)]
    assert payload["incidents"] == []
