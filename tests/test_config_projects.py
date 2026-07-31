"""多项目配置:存储 / 迁移 / 增删改 / 旧 API 兼容。

所有用例通过 monkeypatch app.config.CONFIG_FILE 指向 tmp_path 下的临时文件,
不触碰真实的 config.json。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import config as cfgmod
from app.config import (
    AppConfig,
    DEFAULT_PROJECT_NAME,
    ProjectsConfig,
    active_project,
    create_project,
    delete_project,
    load_config,
    load_projects,
    rename_project,
    save_config,
    set_active,
)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """每个用例独立 config.json,避免污染真实文件。"""
    f = tmp_path / "config.json"
    monkeypatch.setattr(cfgmod, "CONFIG_FILE", f)
    return f


# ---------------- 迁移 ----------------

def write_raw(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_migrate_legacy_flat_format(isolated_config: Path) -> None:
    """旧平铺格式 -> 迁移为单个「默认」项目。"""
    write_raw(isolated_config, {
        "input_dir": "./sample",
        "client_bin": "./out_c",
        "client_lang": "lua",
        "extra_unknown_field": "ignored",  # 多余字段应被忽略
    })
    p = load_projects()
    assert p.active == DEFAULT_PROJECT_NAME
    assert list(p.projects.keys()) == [DEFAULT_PROJECT_NAME]
    cfg = p.projects[DEFAULT_PROJECT_NAME]
    assert cfg.input_dir == "./sample"
    assert cfg.client_bin == "./out_c"
    assert cfg.client_lang == "lua"
    # 多余字段未进入
    assert not hasattr(cfg, "extra_unknown_field")


def test_migration_writes_back_new_format(isolated_config: Path) -> None:
    """旧格式迁移后写回磁盘,二次加载为新格式。"""
    write_raw(isolated_config, {"input_dir": "./sample"})
    load_projects()  # 触发迁移
    # 磁盘上应已是新格式(含 projects 键)
    raw = json.loads(isolated_config.read_text(encoding="utf-8"))
    assert "projects" in raw
    assert DEFAULT_PROJECT_NAME in raw["projects"]
    assert raw["active"] == DEFAULT_PROJECT_NAME
    # 二次加载为新格式,字段不丢
    p2 = load_projects()
    assert p2.projects[DEFAULT_PROJECT_NAME].input_dir == "./sample"


def test_missing_file_creates_default(isolated_config: Path) -> None:
    assert not isolated_config.exists()
    p = load_projects()
    assert list(p.projects.keys()) == [DEFAULT_PROJECT_NAME]
    assert p.active == DEFAULT_PROJECT_NAME


def test_corrupt_file_falls_back(isolated_config: Path) -> None:
    isolated_config.write_text("{not valid json", encoding="utf-8")
    p = load_projects()
    assert DEFAULT_PROJECT_NAME in p.projects


# ---------------- 新格式读写往返 ----------------

def test_new_format_roundtrip(isolated_config: Path) -> None:
    p = ProjectsConfig(projects={
        "A": AppConfig(input_dir="./a", client_lang="go"),
        "B": AppConfig(input_dir="./b", server_lang="lua"),
    }, active="B")
    from app.config import save_projects
    save_projects(p)
    p2 = load_projects()
    assert set(p2.projects.keys()) == {"A", "B"}
    assert p2.active == "B"
    assert p2.projects["A"].client_lang == "go"
    assert p2.projects["B"].server_lang == "lua"


def test_empty_projects_object_falls_back(isolated_config: Path) -> None:
    write_raw(isolated_config, {"projects": {}, "active": ""})
    p = load_projects()
    assert DEFAULT_PROJECT_NAME in p.projects


def test_invalid_active_falls_back_to_first(isolated_config: Path) -> None:
    write_raw(isolated_config, {"projects": {"A": {"input_dir": ""}}, "active": "不存在"})
    p = load_projects()
    assert p.active == "A"


# ---------------- 增删改 ----------------

def test_create_project_dedup(isolated_config: Path) -> None:
    p = load_projects()  # 含「默认」
    create_project(p, "P2")
    with pytest.raises(ValueError, match="已存在"):
        create_project(p, "默认")
    with pytest.raises(ValueError, match="不能为空"):
        create_project(p, "   ")


def test_rename_project_syncs_active(isolated_config: Path) -> None:
    p = load_projects()
    create_project(p, "P2")
    assert p.active == "P2"
    rename_project(p, "P2", "Renamed")
    assert "Renamed" in p.projects and "P2" not in p.projects
    assert p.active == "Renamed"


def test_rename_dedup(isolated_config: Path) -> None:
    p = load_projects()
    create_project(p, "P2")
    with pytest.raises(ValueError, match="已存在"):
        rename_project(p, "P2", "默认")


def test_delete_last_rejected(isolated_config: Path) -> None:
    p = load_projects()  # 仅「默认」
    with pytest.raises(ValueError, match="至少保留"):
        delete_project(p, DEFAULT_PROJECT_NAME)


def test_delete_active_picks_new_active(isolated_config: Path) -> None:
    p = load_projects()
    create_project(p, "P2")
    assert p.active == "P2"
    delete_project(p, "P2")
    assert "P2" not in p.projects
    assert p.active == DEFAULT_PROJECT_NAME


def test_set_active_validation(isolated_config: Path) -> None:
    p = load_projects()
    create_project(p, "P2")
    set_active(p, "默认")
    assert p.active == "默认"
    with pytest.raises(ValueError, match="不存在"):
        set_active(p, "Ghost")


# ---------------- 兼容旧 API ----------------

def test_legacy_load_config_returns_active(isolated_config: Path) -> None:
    p = load_projects()
    create_project(p, "P2")
    p.projects["P2"].input_dir = "./from-P2"
    from app.config import save_projects
    save_projects(p)
    cfg = load_config()
    assert cfg.input_dir == "./from-P2"


def test_legacy_save_config_writes_active(isolated_config: Path) -> None:
    p = load_projects()
    create_project(p, "P2")
    save_config(AppConfig(input_dir="./written"))
    p2 = load_projects()
    assert p2.projects["P2"].input_dir == "./written"
