"""无头 CLI 端到端：projects / build（cs_wf 产物断言 / 失败阻断 / 退出码 / JSON schema）。

协议契约：框架仓 specs/027-excel-table-pipeline/contracts/cli-protocol.md。
config 隔离：monkeypatch CONFIG_FILE 指向 tmp（不触碰真实 config.json，同 test_config_projects）。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import openpyxl
import pytest

from app import config as cfgmod
from app.cli import main
from app.config import AppConfig, ProjectsConfig

ROOT = Path(__file__).parent.parent
SAMPLE = ROOT / "sample" / "Item.xlsx"

GOOD_TABLE = [
    ("##", "int", "string", "int"),
    ("#name", "id", "name", "hp"),
    ("#desc", "主键", "名字", "血量"),
    ("", 1001, "木剑", 50),
    ("", 1002, "铁剑", 90),
]

BAD_TABLE = [
    ("##", "int", "string", "int"),
    ("#name", "id", "name", "hp"),
    ("#desc", "主键", "名字", "血量"),
    ("", 1001, "木剑", 50),
    ("", 1001, "铁剑", 90),  # 主键重复 -> ERROR
]


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    f = tmp_path / "config.json"
    monkeypatch.setattr(cfgmod, "CONFIG_FILE", f)
    return f


@pytest.fixture()
def project(tmp_path: Path, isolated_config: Path) -> str:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    shutil.copy(SAMPLE, input_dir / "Item.xlsx")
    cfgmod.save_projects(ProjectsConfig(
        projects={"demo": AppConfig(input_dir=str(input_dir))},
        active="demo",
    ))
    return "demo"


def _write_table(input_dir: Path, rows, name: str = "Broken.xlsx") -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    wb.save(input_dir / name)
    wb.close()


def test_projects_json(isolated_config: Path, project: str, capsys):
    code = main(["projects", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["projects"] == ["demo"]
    assert out["active"] == "demo"


def test_build_client_cswf_exports_without_table_reader(tmp_path: Path, project: str, capsys):
    bin_dir = tmp_path / "bin"
    cs_dir = tmp_path / "cs"
    code = main([
        "build", "--project", "demo",
        "--client-bin", str(bin_dir), "--client-cs", str(cs_dir),
        "--client-lang", "cs_wf", "--client-ns", "Demo.Tables",
        "--side", "client", "--json",
    ])
    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert code == 0, captured.err
    assert result["ok"] is True
    assert result["error_count"] == 0
    paths = [f["path"].replace("\\", "/") for f in result["files"]]
    assert any(p.endswith("/Item_c.bytes") for p in paths)
    assert any(p.endswith("/ItemData.cs") for p in paths)
    assert any(p.endswith("/ItemTable.cs") for p in paths)
    assert not any("TableReader" in p for p in paths), "cs_wf 不产 TableReader（框架提供）"

    table_src = (cs_dir / "ItemTable.cs").read_text(encoding="utf-8")
    assert '[ConfigTable("Item_c")]' in table_src

    # 人类可读摘要在 stderr（stdout 只有 JSON）
    assert "构建完成" in captured.err


def test_build_overrides_do_not_rewrite_config(tmp_path: Path, project: str, isolated_config: Path, capsys):
    before = isolated_config.read_text(encoding="utf-8")
    main([
        "build", "--project", "demo",
        "--client-bin", str(tmp_path / "b"), "--client-cs", str(tmp_path / "c"),
        "--client-lang", "cs_wf", "--side", "client", "--json",
    ])
    capsys.readouterr()
    assert isolated_config.read_text(encoding="utf-8") == before, "覆盖参数不得回写 config.json"


def test_build_validation_error_blocks_export(tmp_path: Path, project: str, capsys):
    # 主键重复 -> ERROR -> 退出码 1、无产物、JSON 报错
    input_dir = tmp_path / "in"
    _write_table(input_dir, BAD_TABLE, name="Broken.xlsx")
    bin_dir = tmp_path / "bin"
    cs_dir = tmp_path / "cs"

    code = main([
        "build", "--project", "demo",
        "--client-bin", str(bin_dir), "--client-cs", str(cs_dir),
        "--client-lang", "cs_wf", "--side", "client", "--json",
    ])
    result = json.loads(capsys.readouterr().out)

    assert code == 1
    assert result["ok"] is False
    assert result["error_count"] > 0
    assert result["check"]["total_errors"] > 0
    assert not bin_dir.exists() or not any(bin_dir.iterdir()), "阻断导出：不产半成品"


def test_build_unknown_project_usage_error(capsys):
    code = main(["build", "--project", "ghost", "--json"])
    assert code == 2
    assert "ghost" in capsys.readouterr().err


def test_build_missing_input_dir_usage_error(project: str, tmp_path: Path, monkeypatch, capsys):
    cfg = cfgmod.load_projects()
    cfg.projects["demo"].input_dir = ""
    cfgmod.save_projects(cfg)
    code = main(["build", "--project", "demo", "--side", "client", "--json"])
    assert code == 2
    assert "输入目录" in capsys.readouterr().err
