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

from .schema import FieldRule


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


# —— 注册表:加规则的唯一入口 ——
# Task 3-5 会填入具体规则子类
REGISTRY: dict[str, type[Rule]] = {}


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
