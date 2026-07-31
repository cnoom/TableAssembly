"""配置持久化:读写项目根目录下的 config.json。

支持**多项目管理**:一份 config.json 同时保存多套命名配置(项目),
其中一个被标记为「活动」,网页下拉框可一键切换。

文件格式(新):
    {
      "projects": {"默认": {<AppConfig 字段>}, "MMO服务端": {...}},
      "active": "默认"
    }

兼容旧格式(平铺字段,如 {"input_dir": ...}):首次加载时自动迁移为
含单个「默认」项目的新格式并写回磁盘,字段不丢,零摩擦升级。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import MutableMapping

CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.json"

DEFAULT_PROJECT_NAME = "默认"


@dataclass
class AppConfig:
    input_dir: str = ""
    client_bin: str = ""
    client_cs: str = ""
    server_bin: str = ""
    server_cs: str = ""
    client_namespace: str = ""  # 空 -> 按 client_cs 推导
    server_namespace: str = ""  # 空 -> 按 server_cs 推导
    client_lang: str = "cs"  # client 端代码生成语言(可前后端分别指定)
    server_lang: str = "cs"  # server 端代码生成语言(可前后端分别指定)
    subdirs_by_table: bool = False  # 代码文件是否按表名建子目录;默认 False 平铺

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProjectsConfig:
    """多项目配置集合。"""

    projects: dict[str, AppConfig] = field(default_factory=dict)
    active: str = ""  # 活动项目名;空表示无活动

    def to_dict(self) -> dict:
        return {
            "projects": {k: v.to_dict() for k, v in self.projects.items()},
            "active": self.active,
        }

    def project_names(self) -> list[str]:
        return list(self.projects.keys())


# ---------------- 读写(识别旧/新格式 + 迁移) ----------------

def _known_fields() -> set[str]:
    return set(AppConfig().to_dict().keys())


def _config_from_dict(data: dict) -> AppConfig:
    """从 dict 取已知字段构造 AppConfig(忽略多余字段)。"""
    known = _known_fields()
    cleaned = {k: v for k, v in data.items() if k in known}
    return AppConfig(**cleaned)


def load_projects() -> ProjectsConfig:
    """读取 config.json,自动识别新旧格式。

    - 新格式(含 projects 键):直接解析
    - 旧格式(平铺字段):迁移为单个「默认」项目,写回磁盘
    - 文件不存在/解析失败:返回含一个空「默认」项目的结构
    """
    if not CONFIG_FILE.exists():
        return ProjectsConfig(projects={DEFAULT_PROJECT_NAME: AppConfig()}, active=DEFAULT_PROJECT_NAME)

    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return ProjectsConfig(projects={DEFAULT_PROJECT_NAME: AppConfig()}, active=DEFAULT_PROJECT_NAME)

    # 新格式
    if isinstance(data, dict) and "projects" in data and isinstance(data["projects"], dict):
        raw_projects: MutableMapping = data["projects"]
        projects: dict[str, AppConfig] = {}
        for name, fields in raw_projects.items():
            if isinstance(fields, dict):
                projects[name] = _config_from_dict(fields)
        if not projects:  # projects 为空对象,兜底一个默认项目
            projects[DEFAULT_PROJECT_NAME] = AppConfig()
        active = data.get("active", "")
        if active not in projects:  # active 指向不存在的名字,回退第一个
            active = next(iter(projects))
        return ProjectsConfig(projects=projects, active=active)

    # 旧格式(平铺字段) -> 迁移
    if isinstance(data, dict):
        cfg = _config_from_dict(data)
        migrated = ProjectsConfig(projects={DEFAULT_PROJECT_NAME: cfg}, active=DEFAULT_PROJECT_NAME)
        save_projects(migrated)  # 写回磁盘,下次即新格式
        return migrated

    return ProjectsConfig(projects={DEFAULT_PROJECT_NAME: AppConfig()}, active=DEFAULT_PROJECT_NAME)


def save_projects(cfg: ProjectsConfig) -> None:
    """写盘(保证至少有一个项目且 active 有效)。"""
    if not cfg.projects:  # 兜底:禁止空集合
        cfg.projects = {DEFAULT_PROJECT_NAME: AppConfig()}
    if cfg.active not in cfg.projects:
        cfg.active = next(iter(cfg.projects))
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------- 活动项目 / 增删改 ----------------

def active_project(p: ProjectsConfig) -> AppConfig:
    """取活动项目;若 active 失效则修正为第一个并返回。"""
    if p.active in p.projects:
        return p.projects[p.active]
    # 失效,修正
    if p.projects:
        p.active = next(iter(p.projects))
        return p.projects[p.active]
    # 不应发生(save_projects 保证非空),兜底
    p.projects = {DEFAULT_PROJECT_NAME: AppConfig()}
    p.active = DEFAULT_PROJECT_NAME
    return p.projects[p.active]


def create_project(p: ProjectsConfig, name: str) -> AppConfig:
    """新建项目并切为活动。重名抛 ValueError。"""
    name = (name or "").strip()
    if not name:
        raise ValueError("项目名不能为空")
    if name in p.projects:
        raise ValueError("项目名已存在")
    cfg = AppConfig()
    p.projects[name] = cfg
    p.active = name
    save_projects(p)
    return cfg


def rename_project(p: ProjectsConfig, old: str, new: str) -> None:
    """重命名项目。新名重名抛 ValueError。活动项改名则 active 同步。"""
    old = (old or "").strip()
    new = (new or "").strip()
    if not new:
        raise ValueError("项目名不能为空")
    if old not in p.projects:
        raise ValueError(f"项目 {old!r} 不存在")
    if new != old and new in p.projects:
        raise ValueError("项目名已存在")
    # 保持插入顺序:重建 dict
    new_projects: dict[str, AppConfig] = {}
    for k, v in p.projects.items():
        new_projects[new if k == old else k] = v
    p.projects = new_projects
    if p.active == old:
        p.active = new
    save_projects(p)


def delete_project(p: ProjectsConfig, name: str) -> None:
    """删除项目。至少保留一个(删最后一个抛 ValueError)。
    删的是活动项则自动另选活动。"""
    name = (name or "").strip()
    if name not in p.projects:
        raise ValueError(f"项目 {name!r} 不存在")
    if len(p.projects) <= 1:
        raise ValueError("至少保留一个项目,无法删除")
    del p.projects[name]
    if p.active == name:
        p.active = next(iter(p.projects))
    save_projects(p)


def set_active(p: ProjectsConfig, name: str) -> None:
    """切换活动项目。不存在抛 ValueError。"""
    name = (name or "").strip()
    if name not in p.projects:
        raise ValueError(f"项目 {name!r} 不存在")
    p.active = name
    save_projects(p)


# ---------------- 兼容旧 API(单项目) ----------------

def load_config() -> AppConfig:
    """读活动项目配置(兼容旧调用方)。"""
    return active_project(load_projects())


def save_config(cfg: AppConfig) -> None:
    """把 cfg 写回当前活动项目(兼容旧调用方)。"""
    p = load_projects()
    name = p.active if p.active in p.projects else (next(iter(p.projects)) if p.projects else DEFAULT_PROJECT_NAME)
    if not p.projects:
        p.projects = {DEFAULT_PROJECT_NAME: AppConfig()}
        name = DEFAULT_PROJECT_NAME
    p.projects[name] = cfg
    p.active = name
    save_projects(p)
