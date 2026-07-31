"""FastAPI 入口:提供本地网页 + JSON 接口。

接口:
    GET  /                返回可视化网页
    GET  /api/config      读活动项目配置
    POST /api/config      写活动项目配置
    GET  /api/projects    列出所有项目 + 活动名
    POST /api/projects        body={name}         新建项目并切为活动
    PUT  /api/projects/active body={name}         切换活动项目
    POST /api/projects/rename body={old,new}      重命名项目
    DELETE /api/projects      body={name}         删除项目(至少留一个)
    GET  /api/scan        扫描输入目录,返回表列表 + 预解析
    POST /api/check       仅校验,返回诊断
    POST /api/build       校验 + 导出(side=client|server|all)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from . import exporter
from . import markdown_lite
from .config import (
    AppConfig,
    create_project,
    delete_project,
    load_config,
    load_projects,
    rename_project,
    save_config,
    save_projects,
    set_active,
)
from .excel_reader import scan_directory
from .checker import check_all

WEB_DIR = Path(__file__).resolve().parent / "web"

app = FastAPI(title="TableAssembly", version="1.0.0")


# ---------------- 网页 ----------------

@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (WEB_DIR / "index.html").read_text(encoding="utf-8")


# ---------------- 配置 ----------------

class ConfigIn(BaseModel):
    input_dir: str = ""
    client_bin: str = ""
    client_cs: str = ""
    server_bin: str = ""
    server_cs: str = ""
    client_namespace: str = ""
    server_namespace: str = ""
    client_lang: str = "cs"
    server_lang: str = "cs"
    subdirs_by_table: bool = False


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return load_config().to_dict()


@app.post("/api/config")
def set_config(cfg: ConfigIn) -> dict[str, Any]:
    app_cfg = AppConfig(**cfg.model_dump())
    save_config(app_cfg)
    return {"ok": True, "config": app_cfg.to_dict()}


# ---------------- 多项目管理 ----------------

class ProjectNameIn(BaseModel):
    name: str


class ProjectRenameIn(BaseModel):
    old: str
    new: str


@app.get("/api/projects")
def list_projects() -> dict[str, Any]:
    p = load_projects()
    return {
        "ok": True,
        "projects": [{"name": n} for n in p.project_names()],
        "active": p.active,
    }


@app.post("/api/projects")
def api_create_project(body: ProjectNameIn) -> dict[str, Any]:
    p = load_projects()
    try:
        cfg = create_project(p, body.name)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "active": p.active, "config": cfg.to_dict()}


@app.put("/api/projects/active")
def api_set_active(body: ProjectNameIn) -> dict[str, Any]:
    p = load_projects()
    try:
        set_active(p, body.name)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "active": p.active, "config": active_cfg_dict(p)}


@app.post("/api/projects/rename")
def api_rename_project(body: ProjectRenameIn) -> dict[str, Any]:
    p = load_projects()
    try:
        rename_project(p, body.old, body.new)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "active": p.active}


@app.delete("/api/projects")
def api_delete_project(name: str = Query(..., description="要删除的项目名")) -> dict[str, Any]:
    p = load_projects()
    try:
        delete_project(p, name)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "active": p.active, "config": active_cfg_dict(p)}


def active_cfg_dict(p) -> dict[str, Any]:
    """安全取活动项目字段(忽略 p 类型)。"""
    from .config import active_project
    return active_project(p).to_dict()


# ---------------- 扫描 / 预览 ----------------

@app.get("/api/scan")
def api_scan() -> dict[str, Any]:
    cfg = load_config()
    if not cfg.input_dir:
        return {"ok": False, "error": "未配置 input_dir", "tables": []}
    schemas = scan_directory(cfg.input_dir)
    # 附带一次校验结果,前端可直接展示状态
    check = check_all(schemas)
    return {
        "ok": True,
        "tables": [s.to_dict() for s in schemas],
        "check": check.to_dict(),
    }


# ---------------- 仅检查 ----------------

@app.post("/api/check")
def api_check() -> dict[str, Any]:
    cfg = load_config()
    if not cfg.input_dir:
        return {"ok": False, "error": "未配置 input_dir", "check": None}
    schemas = scan_directory(cfg.input_dir)
    check = check_all(schemas)
    return {"ok": True, "check": check.to_dict()}


# ---------------- 构建 ----------------

@app.post("/api/build")
def api_build(side: str = Query("all", pattern="^(client|server|all)$")) -> dict[str, Any]:
    cfg = load_config()
    if not cfg.input_dir:
        return {"ok": False, "error": "未配置 input_dir"}

    exp_cfg = exporter.ExportConfig(
        input_dir=cfg.input_dir,
        client=exporter.SideConfig(
            bin_dir=cfg.client_bin,
            cs_dir=cfg.client_cs,
            namespace_override=cfg.client_namespace,
            lang=cfg.client_lang or "cs",
        ),
        server=exporter.SideConfig(
            bin_dir=cfg.server_bin,
            cs_dir=cfg.server_cs,
            namespace_override=cfg.server_namespace,
            lang=cfg.server_lang or "cs",
        ),
        subdirs_by_table=cfg.subdirs_by_table,
    )

    # side=client/server 时,把另一端的目录临时清空,实现只导一端
    if side == "client":
        exp_cfg.server = exporter.SideConfig()
    elif side == "server":
        exp_cfg.client = exporter.SideConfig()

    result = exporter.export_all(exp_cfg)
    return {"ok": result.ok, "result": result.to_dict()}


# ---------------- 帮助文档 ----------------

@app.get("/api/help")
def api_help() -> dict[str, Any]:
    readme_path = Path(__file__).resolve().parent.parent / "README.md"
    try:
        text = readme_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"ok": False, "error": "README.md 未找到", "sections": []}
    try:
        sections = markdown_lite.split_sections(text)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"文档解析失败: {e}", "sections": []}
    return {"ok": True, "source": "README.md", "sections": sections}
