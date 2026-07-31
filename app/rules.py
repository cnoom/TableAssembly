"""字段级自定义检查规则。

设计(对齐 codegen 的「抽象基类 + 注册表」模式):
    Rule(ABC)            规则抽象基类
    UniqueRule/RangeRule/...   每条规则一个自包含子类
    REGISTRY             注册表,name -> Rule 子类
    parse_rule(text)     把单元格文本段解析成 FieldRule

加新规则 = 新增 Rule 子类 + REGISTRY 注册一行;checker 无需改动。

规则分两类:
    逐值(per-value)  is_aggregate=False,实现 check_value(value, params) -> str|None
    聚合(aggregate)  is_aggregate=True, 实现 check_column(col_values, params) -> list[(row_idx, msg)]

校验时机:checker 在字段循环后调用,按 is_aggregate 分发。
详见 docs/superpowers/specs/2026-07-31-field-rules-design.md。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .schema import (
    FieldRule,
    T_INT,
    T_FLOAT,
    T_STRING,
    T_INT_ARRAY,
    T_FLOAT_ARRAY,
    T_BOOL_ARRAY,
    T_STRING_ARRAY,
)


# 列值序列的类型别名:[(row_index, value), ...];value 为标量或数组
ColValues = list[tuple[int, Any]]


class Rule(ABC):
    """单字段整列规则的抽象基类。每条规则自包含、可独立测试。

    子类通过类属性声明元信息,通过 check_value / check_column 实现具体校验。
    """

    name: str = ""                       # 规则名,如 "range";子类必须覆盖
    applicable_types: set[int] = set()   # 适用 type_code;空集 = 任意类型
    is_aggregate: bool = False           # True=聚合(整列),False=逐值
    n_params: tuple[int, int] = (0, 0)   # 参数个数范围 [min, max]

    @abstractmethod
    def validate_params(self, params: list[str]) -> str | None:
        """参数合法性自检。返回错误消息或 None(合法)。

        基类已校验参数个数(n_params),子类通常只需校验参数含义(如 min<=max)。
        """

    def check_value(self, value: Any, params: list[str]) -> str | None:
        """逐值规则:校验单个值。返回违规消息或 None。

        非聚合规则必须覆盖此方法。聚合规则不应被调用到这里。
        """
        raise NotImplementedError(f"{self.name} 是聚合规则,不支持 check_value")

    def check_column(self, col_values: ColValues, params: list[str]) -> list[tuple[int, str]]:
        """聚合规则:校验整列值。返回 [(row_index, msg), ...]。

        聚合规则必须覆盖此方法。逐值规则不应被调用到这里。
        """
        raise NotImplementedError(f"{self.name} 是逐值规则,不支持 check_column")


# —— 逐值规则 ——


def _parse_bound(token: str) -> float | None | str:
    """解析范围边界。'*' -> None(不限);非法 -> 'ERR' 标记。"""
    t = token.strip()
    if t == "*":
        return None
    try:
        return float(t)
    except ValueError:
        return "ERR"


class NonEmptyRule(Rule):
    name = "non_empty"
    applicable_types = set()  # 任意类型
    is_aggregate = False
    n_params = (0, 0)

    def validate_params(self, params: list[str]) -> str | None:
        return None

    def check_value(self, value: Any, params: list[str]) -> str | None:
        if value is None:
            return "值为空"
        if isinstance(value, list):
            if len(value) == 0:
                return "数组为空"
            return None
        if isinstance(value, str) and value == "":
            return "字符串为空"
        return None


class RangeRule(Rule):
    name = "range"
    applicable_types = {T_INT, T_FLOAT}
    is_aggregate = False
    n_params = (2, 2)

    def validate_params(self, params: list[str]) -> str | None:
        lo = _parse_bound(params[0])
        hi = _parse_bound(params[1])
        if lo == "ERR" or hi == "ERR":
            return f"参数非法(应为数字或 *): {params}"
        if lo is None and hi is None:
            return "range 两边都为 * 无意义"
        if lo is not None and hi is not None and lo > hi:
            return f"下界 {lo} 大于上界 {hi}"
        return None

    def check_value(self, value: Any, params: list[str]) -> str | None:
        lo = _parse_bound(params[0])
        hi = _parse_bound(params[1])
        if lo is not None and value < lo:
            return f"值 {value} 小于下界 {lo:g}"
        if hi is not None and value > hi:
            return f"值 {value} 大于上界 {hi:g}"
        return None


class ElemRangeRule(Rule):
    name = "elem_range"
    applicable_types = {T_INT_ARRAY, T_FLOAT_ARRAY}
    is_aggregate = False
    n_params = (2, 2)

    def validate_params(self, params: list[str]) -> str | None:
        return RangeRule().validate_params(params)

    def check_value(self, value: Any, params: list[str]) -> str | None:
        if not isinstance(value, list):
            return f"elem_range 仅作用于数组,得到 {type(value).__name__}"
        lo = _parse_bound(params[0])
        hi = _parse_bound(params[1])
        for elem in value:
            if lo is not None and elem < lo:
                return f"元素 {elem} 小于下界 {lo:g}"
            if hi is not None and elem > hi:
                return f"元素 {elem} 大于上界 {hi:g}"
        return None


class LenRule(Rule):
    name = "len"
    applicable_types = {T_INT_ARRAY, T_FLOAT_ARRAY, T_BOOL_ARRAY, T_STRING_ARRAY}
    is_aggregate = False
    n_params = (2, 2)

    def validate_params(self, params: list[str]) -> str | None:
        lo = _parse_bound(params[0])
        hi = _parse_bound(params[1])
        if lo == "ERR" or hi == "ERR":
            return f"参数非法(应为整数或 *): {params}"
        if lo is None and hi is None:
            return "len 两边都为 * 无意义"
        if lo is not None and (lo < 0 or not float(lo).is_integer()):
            return f"长度下界必须是非负整数,得到 {params[0]}"
        if hi is not None and (hi < 0 or not float(hi).is_integer()):
            return f"长度上界必须是非负整数,得到 {params[1]}"
        if lo is not None and hi is not None and lo > hi:
            return f"长度下界 {lo:g} 大于上界 {hi:g}"
        return None

    def check_value(self, value: Any, params: list[str]) -> str | None:
        if not isinstance(value, list):
            return f"len 仅作用于数组,得到 {type(value).__name__}"
        n = len(value)
        lo = _parse_bound(params[0])
        hi = _parse_bound(params[1])
        if lo is not None and n < lo:
            return f"长度 {n} 小于下界 {int(lo)}"
        if hi is not None and n > hi:
            return f"长度 {n} 大于上界 {int(hi)}"
        return None


class RegexRule(Rule):
    name = "regex"
    applicable_types = {T_STRING}
    is_aggregate = False
    n_params = (1, 1)

    def validate_params(self, params: list[str]) -> str | None:
        import re
        try:
            re.compile(params[0])
        except re.error as e:
            return f"正则表达式非法: {e}"
        return None

    def check_value(self, value: Any, params: list[str]) -> str | None:
        import re
        if not isinstance(value, str):
            return f"regex 仅作用于 string,得到 {type(value).__name__}"
        if not re.fullmatch(params[0], value):
            return f"值 {value!r} 不匹配正则 {params[0]!r}"
        return None


class InRule(Rule):
    name = "in"
    applicable_types = set()  # 任意标量(值转字符串比较)
    is_aggregate = False
    n_params = (1, 99)  # 至少一个枚举值

    def validate_params(self, params: list[str]) -> str | None:
        return None

    def check_value(self, value: Any, params: list[str]) -> str | None:
        # 统一转字符串比较(Excel 解析后 bool/int 等已是 Python 值)
        token = str(value).strip() if not isinstance(value, bool) else str(value).lower()
        allowed = {p.strip() for p in params}
        # bool 特殊处理:Excel 里 "true"/"false" 已转 bool;枚举通常写字符串
        if token not in allowed:
            return f"值 {value!r} 不在集合 {sorted(allowed)} 内"
        return None


# —— 注册表:加规则的唯一入口 ——
# Task 3-5 会填入具体规则子类
REGISTRY: dict[str, type[Rule]] = {
    "non_empty": NonEmptyRule,
    "range": RangeRule,
    "elem_range": ElemRangeRule,
    "len": LenRule,
    "regex": RegexRule,
    "in": InRule,
}


def parse_rule(text: str) -> FieldRule | None:
    """把单元格文本的一段(已按 rule_sep 切分)解析成 FieldRule。

    空白段返回 None(调用方跳过)。
    解析成功但规则名未知 / 参数个数错,把错误塞进 FieldRule.parse_errors,不抛异常。
    """
    s = text.strip()
    if s == "":
        return None
    # 首个冒号切分:保证 regex:http://... 含冒号 pattern 不被截断
    if ":" in s:
        name, _, raw_params = s.partition(":")
        name = name.strip()
        params = [p.strip() for p in raw_params.split(",")] if raw_params.strip() != "" else []
    else:
        name = s
        params = []

    fr = FieldRule(name=name, params=params, parse_errors=[])
    rule_cls = REGISTRY.get(name)
    if rule_cls is None:
        fr.parse_errors.append(f"未知规则名 {name!r}")
        return fr
    # 参数个数检查
    lo, hi = rule_cls.n_params
    if not (lo <= len(params) <= hi):
        fr.parse_errors.append(f"规则 {name!r} 参数个数错误:期望 {lo}..{hi} 个,实际 {len(params)} 个")
        return fr
    # 参数语义检查(交给子类)
    msg = rule_cls().validate_params(params)
    if msg is not None:
        fr.parse_errors.append(msg)
    return fr
