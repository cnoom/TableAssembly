"""FastAPI 入口:提供本地网页 + JSON 接口。

接口:
    GET  /                返回可视化网页
    GET  /api/config      读配置
    POST /api/config      写配置
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
from .config import AppConfig, load_config, save_config
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
