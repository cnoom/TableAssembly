"""代码生成器抽象基类。

设计:生成器是无状态的语言适配器,但生成需要"命名空间"这类环境信息,
所以采用「工厂函数」模式:exporter 通过 create_generator(name, namespace) 拿到
绑定好环境的实例,再调用 generate()。

新增语言只需实现 CodeGenerator,然后在 codegen/__init__.py 注册工厂。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, List, Protocol

from ..schema import FieldDef, TableSchema


@dataclass
class OutputFile:
    """一个待写入磁盘的生成文件。"""

    relative_path: str  # 相对于「代码输出根目录」的路径,如 "Item/ItemData.cs"
    content: str
    is_shared: bool = False  # 共用文件(如 TableReader.cs),每端只写一次


class CodeGenerator(Protocol):
    """代码生成器协议(实例,已绑定命名空间)。"""

    name: str  # 语言名,如 "cs"

    def generate(
        self,
        schema: TableSchema,
        side: str,  # client / server
        fields: List[FieldDef],
        subdirs_by_table: bool = False,  # 是否按表名建子目录;默认 False 平铺
    ) -> List[OutputFile]:
        """为一张表的一个端生成代码文件。"""

    def shared_files(self) -> List[OutputFile]:
        """所有表共用的文件(如 TableReader.cs)。无则返回空列表。"""


# 工厂类型:namespace -> CodeGenerator 实例
GeneratorFactory = Callable[[str], CodeGenerator]


def derive_namespace(output_dir: str, override: str | None = None) -> str:
    """从输出目录推导默认命名空间;override 非空时直接使用(校验后)。

    规则:
    - override 非空 -> 直接 sanitize 后用
    - 否则取目录最后一段作为根
    - 非法字符:连字符 -> _,数字开头加 _,去空格,其它非 [A-Za-z0-9_] 删掉
    - 全空时回退 "GameData"
    """
    if override and override.strip():
        return _sanitize_namespace(override.strip()) or "GameData"
    name = os.path.basename(os.path.normpath(output_dir)) if output_dir else ""
    return _sanitize_namespace(name) or "GameData"


def _sanitize_namespace(name: str) -> str:
    if not name:
        return ""
    s = name.replace(" ", "").replace("\t", "")
    s = s.replace("-", "_")
    out_chars: list[str] = []
    for ch in s:
        if ch.isalnum() or ch == "_":
            out_chars.append(ch)
    out = "".join(out_chars)
    if not out:
        return ""
    if out[0].isdigit():
        out = "_" + out
    return out
