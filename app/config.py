"""路径配置持久化:读写项目根目录下的 config.json。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.json"


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


def load_config() -> AppConfig:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            # 只取已知字段,避免多余字段干扰
            known = AppConfig().to_dict().keys()
            cleaned = {k: v for k, v in data.items() if k in known}
            return AppConfig(**cleaned)
        except Exception:  # noqa: BLE001
            return AppConfig()
    return AppConfig()


def save_config(cfg: AppConfig) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
