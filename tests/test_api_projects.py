"""多项目管理端点(/api/projects 系列)。

通过 monkeypatch app.config.CONFIG_FILE 隔离真实 config.json,
保证测试不污染用户本地配置。
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """每个用例独立 config.json + 重新导入 app.main(吃下新 CONFIG_FILE)。"""
    f = tmp_path / "config.json"
    # config 模块的 CONFIG_FILE 在 import 时已固定,需 patch
    import app.config as cfgmod
    monkeypatch.setattr(cfgmod, "CONFIG_FILE", f)
    # main 在 import 时 from .config import 了符号,重新导入以绑定新 patch
    import app.main as mainmod
    importlib.reload(mainmod)
    return TestClient(mainmod.app)


# ---------------- 列表 ----------------

def test_list_projects_default(client: TestClient) -> None:
    r = client.get("/api/projects")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    names = [p["name"] for p in body["projects"]]
    assert "默认" in names
    assert body["active"] == "默认"


# ---------------- 新建 ----------------

def test_create_project(client: TestClient) -> None:
    r = client.post("/api/projects", json={"name": "P2"})
    assert r.json()["ok"] is True
    assert r.json()["active"] == "P2"
    # 列表里出现
    names = [p["name"] for p in client.get("/api/projects").json()["projects"]]
    assert "P2" in names


def test_create_duplicate_rejected(client: TestClient) -> None:
    r = client.post("/api/projects", json={"name": "默认"})
    body = r.json()
    assert body["ok"] is False
    assert "已存在" in body["error"]


def test_create_empty_name_rejected(client: TestClient) -> None:
    r = client.post("/api/projects", json={"name": "   "})
    assert r.json()["ok"] is False
    assert "不能为空" in r.json()["error"]


# ---------------- 切换 ----------------

def test_set_active(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "P2"})
    r = client.put("/api/projects/active", json={"name": "默认"})
    assert r.json()["active"] == "默认"
    # GET /api/config 应回到「默认」
    assert client.get("/api/config").json()["input_dir"] == ""


def test_set_active_unknown(client: TestClient) -> None:
    r = client.put("/api/projects/active", json={"name": "Ghost"})
    assert r.json()["ok"] is False


# ---------------- 重命名 ----------------

def test_rename_project(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "P2"})
    r = client.post("/api/projects/rename", json={"old": "P2", "new": "P2Renamed"})
    assert r.json()["ok"] is True
    assert r.json()["active"] == "P2Renamed"
    names = [p["name"] for p in client.get("/api/projects").json()["projects"]]
    assert "P2Renamed" in names and "P2" not in names


def test_rename_to_existing_rejected(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "P2"})
    r = client.post("/api/projects/rename", json={"old": "P2", "new": "默认"})
    assert r.json()["ok"] is False
    assert "已存在" in r.json()["error"]


# ---------------- 删除 ----------------

def test_delete_project(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "P2"})
    r = client.delete("/api/projects", params={"name": "P2"})
    assert r.json()["ok"] is True
    names = [p["name"] for p in client.get("/api/projects").json()["projects"]]
    assert "P2" not in names


def test_delete_last_rejected(client: TestClient) -> None:
    # 仅「默认」一个
    r = client.delete("/api/projects", params={"name": "默认"})
    assert r.json()["ok"] is False
    assert "至少保留" in r.json()["error"]


def test_delete_active_auto_switch(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "P2"})  # 切为活动
    assert client.get("/api/projects").json()["active"] == "P2"
    r = client.delete("/api/projects", params={"name": "P2"})
    assert r.json()["active"] == "默认"


# ---------------- /api/config 与活动项目联动 ----------------

def test_config_get_set_active_project(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "P2"})
    client.post("/api/config", json={"input_dir": "/x", "client_bin": ""})
    # GET 应回到刚写入的 P2
    got = client.get("/api/config").json()
    assert got["input_dir"] == "/x"
    # 切回「默认」应为空
    client.put("/api/projects/active", json={"name": "默认"})
    assert client.get("/api/config").json()["input_dir"] == ""
