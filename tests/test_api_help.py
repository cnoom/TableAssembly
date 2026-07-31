"""GET /api/help 端点。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_help_returns_sections():
    r = client.get("/api/help")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["source"] == "README.md"
    secs = body["sections"]
    assert isinstance(secs, list)
    assert len(secs) >= 8
    titles = [s["title"] for s in secs]
    assert "快速开始" in titles
    for s in secs:
        assert s["id"]
        assert s["title"]
        assert s["html"]  # 非空


def test_help_section_shape():
    r = client.get("/api/help")
    s = r.json()["sections"][0]
    assert set(s.keys()) == {"id", "title", "html"}
