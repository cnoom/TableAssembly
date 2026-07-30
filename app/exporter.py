"""导出编排:解析 -> 校验 -> 按归属分包 -> 写二进制 + 代码。

按 #cs 归属分包:
    client 包 = both 列 + client 列
    server 包 = both 列 + server 列
各自独立的二进制输出目录和代码输出目录。
文件名带后缀: Item_c.bytes / Item_s.bytes。TableReader.cs 各端各一份。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import binary_writer as bw
from . import checker
from . import schema as S
from .codegen import create_generator, derive_namespace
from .codegen.base import CodeGenerator


@dataclass
class SideConfig:
    """单个端(client/server)的输出配置。"""

    bin_dir: str = ""
    cs_dir: str = ""
    namespace_override: str = ""  # 空 -> 按 cs_dir 推导
    lang: str = "cs"  # 该端代码生成语言(可前后端分别指定,如 client=cs / server=lua)


@dataclass
class ExportConfig:
    """整体导出配置。"""

    input_dir: str = ""
    client: SideConfig = field(default_factory=SideConfig)
    server: SideConfig = field(default_factory=SideConfig)
    subdirs_by_table: bool = False  # 代码文件是否按表名建子目录;默认 False 平铺


@dataclass
class FileOutput:
    path: str
    size: int
    kind: str  # "bin" / "cs" / "shared"


@dataclass
class ExportResult:
    ok: bool
    error_count: int
    warning_count: int
    check_result: checker.CheckResult
    files: list[FileOutput] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # 导出过程本身的错误(非数据校验)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "files": [{"path": f.path, "size": f.size, "kind": f.kind} for f in self.files],
            "errors": list(self.errors),
            "check": self.check_result.to_dict(),
        }


# ---------------- 核心导出 ----------------

def export_all(config: ExportConfig, schemas: list[S.TableSchema] | None = None) -> ExportResult:
    """执行:扫描/解析 -> 校验 -> 按归属分包导出。

    schemas 为 None 时自动扫描 config.input_dir。
    若校验存在 ERROR,则不导出任何文件(避免半成品)。
    """
    # 1) 解析
    if schemas is None:
        from .excel_reader import scan_directory

        schemas = scan_directory(config.input_dir)

    # 2) 校验
    check_result = checker.check_all(schemas)
    result = ExportResult(
        ok=check_result.ok,
        error_count=check_result.total_errors,
        warning_count=check_result.total_warnings,
        check_result=check_result,
    )
    if not check_result.ok:
        return result  # 有错误,不导出
    if not schemas:
        return result

    # 3) 按端导出
    for side, side_cfg in (("client", config.client), ("server", config.server)):
        if not side_cfg.bin_dir or not side_cfg.cs_dir:
            result.errors.append(f"{side} 端输出目录未配置(bin/cs),跳过该端")
            continue
        try:
            files = _export_side(schemas, side, side_cfg, config.subdirs_by_table)
            result.files.extend(files)
        except Exception as e:  # noqa: BLE001
            result.errors.append(f"{side} 端导出失败: {e!r}")
            result.ok = False

    return result


def _export_side(
    schemas: list[S.TableSchema], side: str, side_cfg: SideConfig,
    subdirs_by_table: bool = False,
) -> list[FileOutput]:
    """导出单个端的所有表。"""
    namespace = derive_namespace(side_cfg.cs_dir, side_cfg.namespace_override or None)
    lang = side_cfg.lang or "cs"
    gen = create_generator(lang, namespace)
    if gen is None:
        raise ValueError(f"未知代码语言: {lang}")

    bin_root = Path(side_cfg.bin_dir)
    cs_root = Path(side_cfg.cs_dir)
    bin_root.mkdir(parents=True, exist_ok=True)
    cs_root.mkdir(parents=True, exist_ok=True)

    out_files: list[FileOutput] = []
    suffix = "_c" if side == "client" else "_s"

    # —— 先写共用文件(TableReader.cs),每端一份 ——
    for sf in gen.shared_files():
        full = cs_root / sf.relative_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(sf.content, encoding="utf-8")
        out_files.append(FileOutput(str(full), len(sf.content.encode("utf-8")), "shared"))

    # —— 每张表 ——
    for schema in schemas:
        fields = schema.fields_for_side(side)
        if not fields:
            continue  # 该表在本端无可见字段,跳过

        # 二进制
        data = bw.build_binary(schema, fields, schema.rows)
        bin_path = bin_root / f"{schema.name}{suffix}.bytes"
        bin_path.write_bytes(data)
        out_files.append(FileOutput(str(bin_path), len(data), "bin"))

        # 代码
        for cf in gen.generate(schema, side, fields, subdirs_by_table):
            full = cs_root / cf.relative_path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(cf.content, encoding="utf-8")
            out_files.append(FileOutput(str(full), len(cf.content.encode("utf-8")), "cs"))

    return out_files
