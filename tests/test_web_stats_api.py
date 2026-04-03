from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_api_stats_returns_placeholder_during_async_warmup(monkeypatch):
    import web.app as web_app

    started = []

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon
            started.append(self)

        def start(self):
            web_app._stats_warming.set()

    monkeypatch.setattr(web_app.threading, "Thread", FakeThread)
    monkeypatch.setattr(web_app, "_stats_cache", {"data": None, "expires": 0.0})
    web_app._stats_warming.clear()
    web_app.app.config["TESTING"] = True

    with web_app.app.test_client() as client:
        response = client.get("/api/stats")

    data = response.get_json()
    assert response.status_code == 200
    assert data["message"] == "Computing stats..."
    assert data["total_events"] == 0
    assert started
