"""数据模型:解析后的表结构在内存中的表示。

类型编码(type_code),与 binary_writer / codegen 保持一致:
    1 = int     2 = float     3 = bool     4 = string
    5 = int[]   6 = float[]   7 = bool[]   8 = string[]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# —— 类型常量 ——
T_INT = 1
T_FLOAT = 2
T_BOOL = 3
T_STRING = 4
T_INT_ARRAY = 5
T_FLOAT_ARRAY = 6
T_BOOL_ARRAY = 7
T_STRING_ARRAY = 8

# 基础类型名 -> type_code
BASE_TYPES: dict[str, int] = {
    "int": T_INT,
    "float": T_FLOAT,
    "bool": T_BOOL,
    "string": T_STRING,
}

# 基础 type_code -> 对应数组 type_code
ARRAY_OF: dict[int, int] = {
    T_INT: T_INT_ARRAY,
    T_FLOAT: T_FLOAT_ARRAY,
    T_BOOL: T_BOOL_ARRAY,
    T_STRING: T_STRING_ARRAY,
}

# 数组 type_code -> 元素基础 type_code
ELEMENT_OF: dict[int, int] = {v: k for k, v in ARRAY_OF.items()}

# 归属标记合法值
VALID_SIDES = ("both", "client", "server")


@dataclass
class FieldRule:
    """解析后的一条规则(可能含解析期错误)。

    通常应由 ``app.rules.parse_rule`` 构造(它会填充 parse_errors);
    手动构造时若 name 不在 rules.REGISTRY,checker 会静默跳过该规则(不报错、不执行)。

    由 excel_reader 从 #rule 行切分得到;checker 负责:
    1) 回显 parse_errors(规则名未知、参数个数错等)
    2) 按 name 查(后续提供的)REGISTRY 执行校验
    """

    name: str  # 规则名,如 "range"
    params: list[str]  # 参数,如 ["0", "99999"];无参数规则为空列表
    parse_errors: list[str]  # 解析期问题;空表示解析成功

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "params": list(self.params),
            "parse_errors": list(self.parse_errors),
        }


@dataclass
class FieldDef:
    """一个字段的定义。"""

    name: str  # 字段名(#name 行),代码用标识符
    type_code: int  # 1..8
    sep: str  # 数组分隔符;非数组时为 ""
    desc: str  # 字段说明(#desc 行)
    side: str  # both/client/server
    rules: list[FieldRule] = field(default_factory=list)  # #rule 行声明的规则

    @property
    def is_array(self) -> bool:
        return self.type_code in (T_INT_ARRAY, T_FLOAT_ARRAY, T_BOOL_ARRAY, T_STRING_ARRAY)

    @property
    def element_type(self) -> int:
        """数组元素的基础 type_code;非数组返回自身。"""
        return ELEMENT_OF.get(self.type_code, self.type_code)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type_code": self.type_code,
            "type_name": type_code_to_name(self.type_code),
            "is_array": self.is_array,
            "sep": self.sep,
            "desc": self.desc,
            "side": self.side,
            "rules": [r.to_dict() for r in self.rules],
        }


@dataclass
class DataRow:
    """一行数据。key 为主键值(B 列),values 按字段顺序(含主键)。"""

    key: Any
    values: list[Any] = field(default_factory=list)
    row_index: int = 0  # 在 Excel 中的行号(1-based),便于报错定位


@dataclass
class TableSchema:
    """一张表解析后的完整结构。"""

    name: str  # 表名(去扩展名)
    file_name: str  # 原文件名(含扩展名)
    fields: list[FieldDef] = field(default_factory=list)
    rows: list[DataRow] = field(default_factory=list)
    # 解析阶段的原始诊断(读表时的结构性问题,如缺定义行);checker 会补充数据级诊断
    parse_errors: list[str] = field(default_factory=list)
    rule_sep: str = ";"  # #rule 行多条规则的分隔符;从 #rule[sep=...] 读,默认 ";"

    @property
    def key_field(self) -> FieldDef | None:
        """主键字段(第一个字段 = B 列)。"""
        return self.fields[0] if self.fields else None

    def fields_for_side(self, side: str) -> list[FieldDef]:
        """该端可见的字段:both 总是可见;client 端含 both+client;server 端含 both+server。
        保持字段原始顺序(主键一定在前)。"""
        if side == "client":
            return [f for f in self.fields if f.side in ("both", "client")]
        if side == "server":
            return [f for f in self.fields if f.side in ("both", "server")]
        return list(self.fields)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "file_name": self.file_name,
            "fields": [f.to_dict() for f in self.fields],
            "row_count": len(self.rows),
            "parse_errors": list(self.parse_errors),
            "rule_sep": self.rule_sep,
        }


def type_code_to_name(code: int) -> str:
    """type_code -> 人类可读类型名。"""
    return {
        T_INT: "int",
        T_FLOAT: "float",
        T_BOOL: "bool",
        T_STRING: "string",
        T_INT_ARRAY: "int[]",
        T_FLOAT_ARRAY: "float[]",
        T_BOOL_ARRAY: "bool[]",
        T_STRING_ARRAY: "string[]",
    }.get(code, f"unknown({code})")
