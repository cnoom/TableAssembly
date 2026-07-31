"""数据校验引擎:对 TableSchema 做静态检查,产出分级诊断。

级别:
    ERROR   阻断导出
    WARNING 可继续,提示
    INFO    通过信息(如 OK 报告)
"""
from __future__ import annotations

import keyword
import re
from dataclasses import dataclass, field
from typing import Any

from . import schema as S
from . import rules as R
from .schema import TableSchema

LEVEL_ERROR = "ERROR"
LEVEL_WARNING = "WARNING"
LEVEL_INFO = "INFO"

# 合法标识符(C# / 通用)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_rule_empty(value: Any) -> bool:
    """规则校验的空值判定:None / 空串 / 空数组视为空(由 non_empty 管)。

    对应空值策略 D8:逐值规则遇空值跳过,空值统一由 non_empty 显式管理,
    避免 range/regex/len 等规则对空值重复报错。
    """
    if value is None:
        return True
    if isinstance(value, str) and value == "":
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    return False


@dataclass
class Issue:
    table: str
    level: str  # ERROR / WARNING / INFO
    row: int | None  # Excel 行号(1-based);表级问题为 None
    col: str | None  # 列名或列字母;表级问题为 None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "level": self.level,
            "row": self.row,
            "col": self.col,
            "message": self.message,
        }


@dataclass
class TableReport:
    table: str
    ok: bool = True  # 无 ERROR 即为 True;过程中按需更新
    error_count: int = 0
    warning_count: int = 0
    issues: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "ok": self.ok,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [i.to_dict() for i in self.issues],
        }


@dataclass
class CheckResult:
    tables: list[TableReport] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(t.ok for t in self.tables)

    @property
    def total_errors(self) -> int:
        return sum(t.error_count for t in self.tables)

    @property
    def total_warnings(self) -> int:
        return sum(t.warning_count for t in self.tables)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "total_errors": self.total_errors,
            "total_warnings": self.total_warnings,
            "tables": [t.to_dict() for t in self.tables],
        }


# ---------------- 单表检查 ----------------

def check_table(schema: TableSchema) -> TableReport:
    """对单张表做完整检查。"""
    rep = TableReport(table=schema.name)

    def add(level: str, message: str, row: int | None = None, col: str | None = None) -> None:
        rep.issues.append(Issue(schema.name, level, row, col, message))
        if level == LEVEL_ERROR:
            rep.error_count += 1
        elif level == LEVEL_WARNING:
            rep.warning_count += 1

    # 1) 先回显 reader 阶段的结构性错误
    for msg in schema.parse_errors:
        add(LEVEL_ERROR, msg)

    # 2) 字段级检查
    if not schema.fields:
        add(LEVEL_ERROR, "没有任何可用字段")
        rep.ok = rep.error_count == 0
        return rep

    field_names: dict[str, int] = {}
    for i, fdef in enumerate(schema.fields):
        col_letter = chr(ord("A") + i + 1)  # B 列起
        # 标识符合法性
        if not _IDENT_RE.match(fdef.name):
            add(LEVEL_WARNING, f"字段名 {fdef.name!r} 不是合法标识符(可能影响代码生成)", col=fdef.name)
        elif keyword.iskeyword(fdef.name) or fdef.name in ("int", "float", "bool", "string"):
            add(LEVEL_WARNING, f"字段名 {fdef.name!r} 是关键字/保留字,建议改名", col=fdef.name)
        # 重名
        if fdef.name in field_names:
            add(LEVEL_WARNING, f"字段名 {fdef.name!r} 重复(首次列 {chr(ord('A') + field_names[fdef.name] + 1)})", col=fdef.name)
        else:
            field_names[fdef.name] = i

    # 3) 主键列类型必须是标量(不允许主键是数组)
    key_field = schema.key_field
    if key_field and key_field.is_array:
        add(LEVEL_ERROR, f"主键字段 {key_field.name!r} 是数组类型,主键必须是标量", col=key_field.name)

    # 4) 数据行检查:主键非空、主键唯一、每格类型、必填、空数组警告
    seen_keys: dict[str, int] = {}  # key 文本 -> Excel 行号
    for drow in schema.rows:
        # 主键非空(用原始文本 key,reader 里已是字符串)
        key_text = drow.key
        if key_text is None or str(key_text).strip() == "":
            add(LEVEL_ERROR, "主键为空", row=drow.row_index, col=key_field.name if key_field else "B")
            continue
        # 主键唯一
        if key_text in seen_keys:
            add(
                LEVEL_ERROR,
                f"主键 {key_text!r} 重复(首次出现于行 {seen_keys[key_text]})",
                row=drow.row_index,
                col=key_field.name if key_field else "B",
            )
            continue
        seen_keys[key_text] = drow.row_index

        # 每个字段格子校验
        for i, fdef in enumerate(schema.fields):
            if i >= len(drow.values):
                add(LEVEL_ERROR, f"字段 {fdef.name!r} 缺值(行数据列数不足)", row=drow.row_index, col=fdef.name)
                continue
            raw = drow.values[i]
            # reader 已经解析过;这里再走一次解析来产生精确诊断(因为 reader 失败时置 None)
            # 我们没有保留原始文本,所以对 None 且类型非法的情况给出提示
            if raw is None:
                # 区分"reader 解析失败"和"该字段确实缺值"
                add(LEVEL_ERROR, f"字段 {fdef.name!r} 值无法解析为 {S.type_code_to_name(fdef.type_code)}", row=drow.row_index, col=fdef.name)
                continue
            # 必填/空数组提示
            if fdef.is_array and isinstance(raw, list) and len(raw) == 0:
                add(LEVEL_WARNING, f"字段 {fdef.name!r} 为空数组", row=drow.row_index, col=fdef.name)

    # 5) 自定义规则校验(#rule 行声明)
    for fi, fdef in enumerate(schema.fields):
        if not fdef.rules:
            continue
        col_values = [
            (drow.row_index, drow.values[fi] if fi < len(drow.values) else None)
            for drow in schema.rows
        ]
        for fr in fdef.rules:
            # L2:回显解析期错误(规则名未知 / 参数错)
            for pmsg in fr.parse_errors:
                add(LEVEL_ERROR, f"规则 {fr.name!r}: {pmsg}", col=fdef.name)
            if fr.parse_errors:
                continue  # 解析失败的规则不再执行
            rule_cls = R.REGISTRY.get(fr.name)
            if rule_cls is None:
                continue  # 已被 L2 记录,跳过
            # L3:类型守卫
            if rule_cls.applicable_types and fdef.type_code not in rule_cls.applicable_types:
                add(
                    LEVEL_ERROR,
                    f"规则 {fr.name!r} 不适用于类型 {S.type_code_to_name(fdef.type_code)!r}",
                    col=fdef.name,
                )
                continue
            # 执行校验
            if rule_cls.is_aggregate:
                for row_idx, msg in rule_cls().check_column(col_values, fr.params):
                    add(LEVEL_ERROR, f"{fr.name} 字段 {fdef.name!r}: {msg}", row=row_idx, col=fdef.name)
            else:
                for row_idx, val in col_values:
                    # 空值跳过(non_empty 除外):D8 策略
                    if _is_rule_empty(val) and fr.name != "non_empty":
                        continue
                    msg = rule_cls().check_value(val, fr.params)
                    if msg:
                        add(LEVEL_ERROR, f"{fr.name} 字段 {fdef.name!r}: {msg}", row=row_idx, col=fdef.name)

    if rep.error_count == 0:
        add(LEVEL_INFO, f"OK,{len(schema.rows)} 行,{len(schema.fields)} 字段(主键 {key_field.name if key_field else '?'})")
    rep.ok = rep.error_count == 0
    return rep


def check_all(schemas: list[TableSchema]) -> CheckResult:
    """对一组表做检查。"""
    res = CheckResult()
    for s in schemas:
        res.tables.append(check_table(s))
    return res
