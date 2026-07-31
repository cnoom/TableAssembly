# 表字段自定义检查规则(单字段整列规则)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 TableAssembly 中支持 `#rule` 定义行,让策划在 Excel 里对字段声明单字段整列规则(如 `range:0,99999`、`unique`、`regex:^\d{4}$`),checker 阶段强制校验,违规阻断导出。

**Architecture:** 新增独立模块 `app/rules.py`,采用「Rule 抽象基类 + REGISTRY 注册表」模式(对齐现有 `codegen` 扩展模式)。`excel_reader` 识别 `#rule` 行并填充 `FieldDef.rules`;`checker` 调度规则校验,违规复用现有 `Issue` 结构(网页零改动)。规则分两类:逐值(per-value)与聚合(aggregate)。

**Tech Stack:** Python 3.12,openpyxl 3.1,pytest(本计划首次引入测试),FastAPI(网页端基本不改)。

**Spec:** `docs/superpowers/specs/2026-07-31-field-rules-design.md`

---

## 文件结构

| 文件 | 责任 | 动作 |
|------|------|------|
| `app/rules.py` | Rule 抽象基类 + 9 个规则子类 + REGISTRY + 解析/校验公共接口 | 新建 |
| `app/schema.py` | `FieldRule` 数据类;`FieldDef.rules`;`TableSchema.rule_sep`;`to_dict` 扩展 | 修改 |
| `app/excel_reader.py` | 识别 `#rule[sep=]` 行、两层切分、累加去重、稀疏、列对齐 | 修改 |
| `app/checker.py` | 字段循环后调度规则;L2 回显;空值跳过;聚合定位 | 修改 |
| `tests/test_rules.py` | 9 条规则的 validate_params / check_value / check_column | 新建 |
| `tests/test_excel_reader_rules.py` | `#rule` 行解析:多行累加、去重、稀疏、sep、两层切分 | 新建 |
| `tests/test_checker_rules.py` | 规则调度、L2/L3 错误、空值跳过、聚合定位 | 新建 |
| `tests/conftest.py` | 构造 `TableSchema` 的 helper | 新建 |
| `sample/ItemRules.xlsx` | 带 `#rule` 的样例表,供手动验证 | 新建 |
| `requirements.txt` | 加 `pytest` | 修改 |
| `README.md` | 「表格式规范」加 `#rule` 说明;「校验规则」加自定义规则表 | 修改 |

**TDD 原则:** 每个任务先写失败测试,再写实现。逐值/聚合规则各自先测试再实现。

---

## Task 0:引入 pytest 测试基建

**Files:**
- Modify: `requirements.txt`
- Create: `tests/conftest.py`

- [ ] **Step 1: 加 pytest 依赖**

修改 `requirements.txt`,末尾追加一行:

```
pytest>=8.0.0
```

- [ ] **Step 2: 安装**

Run: `pip install pytest`
Expected: 成功

- [ ] **Step 3: 创建 conftest helper**

创建 `tests/conftest.py`:

```python
"""测试公用 helper:构造 TableSchema / FieldDef / DataRow。"""
from __future__ import annotations

from app.schema import FieldDef, DataRow, TableSchema


def make_field(
    name: str,
    type_code: int,
    sep: str = "",
    side: str = "both",
    rules=None,
) -> FieldDef:
    return FieldDef(name=name, type_code=type_code, sep=sep, desc="", side=side, rules=rules or [])


def make_schema(
    name: str = "Test",
    fields: list[FieldDef] | None = None,
    rows: list[tuple] | None = None,  # [(row_index, [val_per_field]), ...]
) -> TableSchema:
    """rows 形如 [(5, [1001, "木剑"]), (6, [1002, "铁剑"])]。
    每个 tuple 的第二个 list 按字段顺序给值。
    """
    s = TableSchema(name=name, file_name=f"{name}.xlsx")
    s.fields = fields or []
    for row_index, vals in (rows or []):
        s.rows.append(DataRow(key=vals[0] if vals else None, values=list(vals), row_index=row_index))
    return s
```

- [ ] **Step 4: 验证可导入**

Run: `python -c "from tests.conftest import make_schema, make_field; print('ok')"`
Expected: 输出 `ok`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt tests/conftest.py
git commit -m "test: 引入 pytest 基建与 conftest helper"
```

---

## Task 1:扩展数据模型(FieldRule / FieldDef.rules / TableSchema.rule_sep)

**Files:**
- Modify: `app/schema.py` (在 `FieldDef` 之前加 `FieldRule`;`FieldDef` 加字段;`TableSchema` 加字段;扩展两个 `to_dict`)
- Test: `tests/test_schema_rules.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_schema_rules.py`:

```python
"""schema 扩展:FieldRule / FieldDef.rules / TableSchema.rule_sep 的结构与 to_dict。"""
from app.schema import FieldDef, FieldRule, TableSchema


def test_field_rule_basic():
    r = FieldRule(name="range", params=["0", "99999"], parse_errors=[])
    assert r.name == "range"
    assert r.params == ["0", "99999"]
    assert r.parse_errors == []


def test_field_rule_no_params():
    r = FieldRule(name="unique", params=[], parse_errors=[])
    assert r.params == []


def test_field_def_has_rules_default_empty():
    f = FieldDef(name="id", type_code=1, sep="", desc="", side="both")
    assert f.rules == []


def test_field_def_with_rules():
    f = FieldDef(
        name="id", type_code=1, sep="", desc="", side="both",
        rules=[FieldRule(name="unique", params=[], parse_errors=[])],
    )
    assert len(f.rules) == 1
    assert f.rules[0].name == "unique"


def test_table_schema_rule_sep_default():
    s = TableSchema(name="T", file_name="T.xlsx")
    assert s.rule_sep == ";"


def test_field_def_to_dict_includes_rules():
    f = FieldDef(
        name="hp", type_code=1, sep="", desc="血量", side="both",
        rules=[FieldRule(name="range", params=["0", "99999"], parse_errors=[])],
    )
    d = f.to_dict()
    assert d["rules"] == [{"name": "range", "params": ["0", "99999"], "parse_errors": []}]


def test_field_def_to_dict_no_rules_empty_list():
    f = FieldDef(name="hp", type_code=1, sep="", desc="", side="both")
    d = f.to_dict()
    assert d["rules"] == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_schema_rules.py -v`
Expected: FAIL — `cannot import name 'FieldRule'`

- [ ] **Step 3: 在 schema.py 加 FieldRule(放在 FieldDef 之前)**

在 `app/schema.py` 的 `FieldDef` 类定义**之前**(`@dataclass class FieldDef` 行之前)插入:

```python
@dataclass
class FieldRule:
    """解析后的一条规则(可能含解析期错误)。

    由 excel_reader 从 #rule 行切分得到;checker 负责:
    1) 回显 parse_errors(规则名未知、参数个数错等)
    2) 按 name 查 REGISTRY 执行校验
    """

    name: str  # 规则名,如 "range"
    params: list[str]  # 参数,如 ["0", "99999"];无参数规则为空列表
    parse_errors: list[str]  # 解析期问题;空表示解析成功
```

- [ ] **Step 4: FieldDef 加 rules 字段**

修改 `app/schema.py` 的 `FieldDef`,在 `side: str` 之后加一行:

```python
    side: str  # both/client/server
    rules: list["FieldRule"] = field(default_factory=list)  # #rule 行声明的规则
```

- [ ] **Step 5: FieldDef.to_dict 加 rules**

修改 `FieldDef.to_dict` 的返回 dict,加一个键(在 `"side"` 后):

```python
            "side": self.side,
            "rules": [{"name": r.name, "params": list(r.params), "parse_errors": list(r.parse_errors)} for r in self.rules],
```

- [ ] **Step 6: TableSchema 加 rule_sep 字段**

修改 `app/schema.py` 的 `TableSchema`,在 `parse_errors` 字段之后加:

```python
    parse_errors: list[str] = field(default_factory=list)
    rule_sep: str = ";"  # #rule 行多条规则的分隔符;从 #rule[sep=...] 读,默认 ";"
```

- [ ] **Step 7: 运行测试确认通过**

Run: `pytest tests/test_schema_rules.py -v`
Expected: 7 passed

- [ ] **Step 8: 跑全量回归确认没破坏现有功能**

Run: `python -c "from app.schema import TableSchema, FieldDef; from app import checker, excel_reader; print('imports ok')"`
Expected: 输出 `imports ok`

- [ ] **Step 9: Commit**

```bash
git add app/schema.py tests/test_schema_rules.py
git commit -m "feat(schema): 新增 FieldRule / FieldDef.rules / TableSchema.rule_sep"
```

---

## Task 2:Rule 抽象基类 + REGISTRY 骨架(无规则子类)

**Files:**
- Create: `app/rules.py`
- Test: `tests/test_rules_registry.py`

本任务只搭骨架(基类、REGISTRY dict、`parse_rule` 接口),规则子类放 Task 3–5。这样能在加规则前先验证解析逻辑。

- [ ] **Step 1: 写失败测试(解析与注册表查询)**

创建 `tests/test_rules_registry.py`:

```python
"""rules.py 骨架:parse_rule 切分、REGISTRY 查询、空段处理。"""
import pytest

from app import rules
from app.rules import parse_rule, REGISTRY


def test_parse_rule_no_params():
    fr = parse_rule("unique")
    assert fr.name == "unique"
    assert fr.params == []
    assert fr.parse_errors == []


def test_parse_rule_with_params():
    fr = parse_rule("range:0,99999")
    assert fr.name == "range"
    assert fr.params == ["0", "99999"]
    assert fr.parse_errors == []


def test_parse_rule_regex_keeps_colon_in_pattern():
    """首个冒号切分,regex pattern 含冒号不被截断。"""
    fr = parse_rule("regex:http://x|ftp://y")
    assert fr.name == "regex"
    assert fr.params == ["http://x|ftp://y"]


def test_parse_rule_in_with_commas():
    fr = parse_rule("in:both,client,server")
    assert fr.name == "in"
    assert fr.params == ["both", "client", "server"]


def test_parse_rule_empty_string_skipped():
    """空段(reader 切分残留)返回 None,调用方跳过。"""
    assert parse_rule("") is None
    assert parse_rule("   ") is None


def test_parse_rule_unknown_name_records_error():
    fr = parse_rule("foobar:1,2")
    assert fr.name == "foobar"
    assert fr.parse_errors  # 非空,有错误消息


def test_registry_lookup_returns_class():
    cls = REGISTRY.get("unique")
    assert cls is not None
    assert cls.name == "unique"


def test_registry_unknown_returns_none():
    assert REGISTRY.get("nope") is None
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_rules_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.rules'`

- [ ] **Step 3: 创建 rules.py 骨架**

创建 `app/rules.py`:

```python
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
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/test_rules_registry.py -v`
Expected:
- `test_parse_rule_*`(5 个)、`test_parse_rule_empty_string_skipped` 通过
- `test_parse_rule_unknown_name_records_error` 通过(REGISTRY 暂空,任何 name 都未知 → 报错,符合)
- `test_registry_lookup_returns_none` 通过
- `test_registry_lookup_returns_class` **FAIL**(REGISTRY 还没规则子类)

注意:`test_registry_lookup_returns_class` 会失败是预期的,Task 3 注册 `UniqueRule` 后会通过。**临时跳过它**:

把 `tests/test_rules_registry.py` 里 `test_registry_lookup_returns_class` 上方加装饰器:

```python
@pytest.mark.skip(reason="Task 3 注册 UniqueRule 后取消跳过")
def test_registry_lookup_returns_class():
```

- [ ] **Step 5: Commit**

```bash
git add app/rules.py tests/test_rules_registry.py
git commit -m "feat(rules): Rule 抽象基类 + REGISTRY + parse_rule 解析接口"
```

---

## Task 3:逐值规则 Part 1 — `non_empty` / `range` / `elem_range`

**Files:**
- Modify: `app/rules.py`(在 REGISTRY 之前加规则子类)
- Test: `tests/test_rules_per_value.py`

逐值规则逐个值校验,实现 `check_value`。本任务做 3 条标量/数值相关的。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_rules_per_value.py`:

```python
"""逐值规则:non_empty / range / elem_range。"""
import pytest

from app.schema import T_INT, T_FLOAT, T_STRING, T_INT_ARRAY, T_STRING_ARRAY
from app.rules import REGISTRY


# —— non_empty ——
def test_non_empty_ok_scalar():
    R = REGISTRY["non_empty"]()
    assert R.check_value(100, []) is None
    assert R.check_value("x", []) is None


def test_non_empty_scalar_violation():
    R = REGISTRY["non_empty"]()
    assert R.check_value("", []) is not None
    assert R.check_value(None, []) is not None


def test_non_empty_array_ok():
    R = REGISTRY["non_empty"]()
    assert R.check_value([1, 2], []) is None


def test_non_empty_array_violation():
    R = REGISTRY["non_empty"]()
    assert R.check_value([], []) is not None


def test_non_empty_metadata():
    R = REGISTRY["non_empty"]
    assert R.is_aggregate is False
    assert R.n_params == (0, 0)


# —— range ——
def test_range_int_ok():
    R = REGISTRY["range"]()
    assert R.check_value(50, ["0", "99999"]) is None
    assert R.check_value(0, ["0", "99999"]) is None
    assert R.check_value(99999, ["0", "99999"]) is None


def test_range_int_violation_below():
    R = REGISTRY["range"]()
    assert R.check_value(-1, ["0", "99999"]) is not None


def test_range_int_violation_above():
    R = REGISTRY["range"]()
    assert R.check_value(100000, ["0", "99999"]) is not None


def test_range_wildcard_upper():
    R = REGISTRY["range"]()
    assert R.check_value(10 ** 9, ["0", "*"]) is None
    assert R.check_value(-1, ["0", "*"]) is not None


def test_range_wildcard_lower():
    R = REGISTRY["range"]()
    assert R.check_value(-10 ** 9, ["*", "0"]) is None
    assert R.check_value(1, ["*", "0"]) is not None


def test_range_float_ok():
    R = REGISTRY["range"]()
    assert R.check_value(1.5, ["0", "2"]) is None


def test_range_validate_params_star_star_errors():
    R = REGISTRY["range"]()
    assert R.validate_params(["*", "*"]) is not None  # 两边都不限,无意义


def test_range_validate_params_non_numeric():
    R = REGISTRY["range"]()
    assert R.validate_params(["abc", "10"]) is not None


def test_range_metadata():
    R = REGISTRY["range"]
    assert R.n_params == (2, 2)
    assert T_INT in R.applicable_types


# —— elem_range ——
def test_elem_range_all_ok():
    R = REGISTRY["elem_range"]()
    assert R.check_value([10, 20, 30], ["1", "9999"]) is None


def test_elem_range_one_violation():
    R = REGISTRY["elem_range"]()
    assert R.check_value([10, 0, 30], ["1", "9999"]) is not None


def test_elem_range_empty_array_skipped():
    """空数组:逐值规则由 checker 的空值跳过策略处理,这里不报。"""
    R = REGISTRY["elem_range"]()
    assert R.check_value([], ["1", "9999"]) is None


def test_elem_range_validate_params():
    R = REGISTRY["elem_range"]()
    assert R.validate_params(["1", "9999"]) is None
    assert R.validate_params(["x", "9"]) is not None
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_rules_per_value.py -v`
Expected: FAIL — `KeyError: 'non_empty'`

- [ ] **Step 3: 在 rules.py 的 REGISTRY 之前加这 3 个子类**

在 `app/rules.py` 的 `# —— 注册表 ——` 行**之前**插入:

```python
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
```

注意:`ElemRangeRule` 引用了 `T_INT_ARRAY` / `T_FLOAT_ARRAY`,在 `app/rules.py` 顶部 import 段补一行:

```python
from .schema import FieldRule, T_INT, T_FLOAT, T_STRING, T_INT_ARRAY, T_FLOAT_ARRAY
```

- [ ] **Step 4: 注册这 3 个规则**

在 `app/rules.py` 的 `REGISTRY` 字典里填入(Task 2 留空的 dict):

```python
REGISTRY: dict[str, type[Rule]] = {
    "non_empty": NonEmptyRule,
    "range": RangeRule,
    "elem_range": ElemRangeRule,
}
```

- [ ] **Step 5: 运行逐值规则测试**

Run: `pytest tests/test_rules_per_value.py -v`
Expected: all passed

- [ ] **Step 6: 取消 Task 2 的 skip,验证注册表测试全过**

编辑 `tests/test_rules_registry.py`,删除 `test_registry_lookup_returns_class` 上的 `@pytest.mark.skip(...)` 装饰器。

Run: `pytest tests/test_rules_registry.py tests/test_rules_per_value.py -v`
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add app/rules.py tests/test_rules_per_value.py tests/test_rules_registry.py
git commit -m "feat(rules): 逐值规则 non_empty / range / elem_range"
```

---

## Task 4:逐值规则 Part 2 — `len` / `regex` / `in`

**Files:**
- Modify: `app/rules.py`
- Test: `tests/test_rules_per_value2.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_rules_per_value2.py`:

```python
"""逐值规则:len / regex / in。"""
from app.rules import REGISTRY


# —— len ——
def test_len_ok():
    R = REGISTRY["len"]()
    assert R.check_value([1, 2, 3], ["1", "5"]) is None


def test_len_too_few():
    R = REGISTRY["len"]()
    assert R.check_value([], ["1", "5"]) is not None


def test_len_too_many():
    R = REGISTRY["len"]()
    assert R.check_value([1, 2, 3, 4, 5, 6], ["1", "5"]) is not None


def test_len_validate_params_star_star():
    R = REGISTRY["len"]()
    assert R.validate_params(["*", "*"]) is not None


def test_len_validate_params_non_int():
    R = REGISTRY["len"]()
    assert R.validate_params(["x", "5"]) is not None


# —— regex ——
def test_regex_match():
    R = REGISTRY["regex"]()
    assert R.check_value("1234", [r"^\d{4}$"]) is None


def test_regex_no_match():
    R = REGISTRY["regex"]()
    assert R.check_value("abc", [r"^\d{4}$"]) is not None


def test_regex_fullmatch_semantics():
    """用 fullmatch,不能部分匹配。"""
    R = REGISTRY["regex"]()
    assert R.check_value("12345", [r"\d{4}"]) is not None  # 多一位不匹配


def test_regex_metadata():
    R = REGISTRY["regex"]
    assert T_STRING_marker := True  # 占位,下面正经断言


def test_regex_applicable_types():
    from app.schema import T_STRING
    R = REGISTRY["regex"]
    assert T_STRING in R.applicable_types


# —— in ——
def test_in_ok():
    R = REGISTRY["in"]()
    assert R.check_value("both", ["both", "client", "server"]) is None


def test_in_violation():
    R = REGISTRY["in"]()
    assert R.check_value("all", ["both", "client", "server"]) is not None


def test_in_single_value():
    R = REGISTRY["in"]()
    assert R.check_value("x", ["x"]) is None
```

修正:`test_regex_metadata` 写错了,删掉这个占位测试函数(保留 `test_regex_applicable_types`)。最终 `tests/test_rules_per_value2.py` 不应含 `test_regex_metadata`。

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_rules_per_value2.py -v`
Expected: FAIL — `KeyError: 'len'`

- [ ] **Step 3: 在 rules.py 的 REGISTRY 之前(逐值规则区)追加这 3 个子类**

在 `app/rules.py` 的 `class ElemRangeRule` 定义**之后**、`# —— 注册表 ——` 之前插入:

```python
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
```

补充 import:`T_BOOL_ARRAY` / `T_STRING_ARRAY` 也需要,更新 `app/rules.py` 顶部 import:

```python
from .schema import (
    FieldRule,
    T_INT, T_FLOAT, T_STRING,
    T_INT_ARRAY, T_FLOAT_ARRAY, T_BOOL_ARRAY, T_STRING_ARRAY,
)
```

- [ ] **Step 4: 注册这 3 个规则**

在 `app/rules.py` 的 `REGISTRY` 字典追加:

```python
REGISTRY: dict[str, type[Rule]] = {
    "non_empty": NonEmptyRule,
    "range": RangeRule,
    "elem_range": ElemRangeRule,
    "len": LenRule,
    "regex": RegexRule,
    "in": InRule,
}
```

- [ ] **Step 5: 运行测试**

Run: `pytest tests/test_rules_per_value2.py -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add app/rules.py tests/test_rules_per_value2.py
git commit -m "feat(rules): 逐值规则 len / regex / in"
```

---

## Task 5:聚合规则 — `unique` / `sorted` / `sorted_desc`

**Files:**
- Modify: `app/rules.py`
- Test: `tests/test_rules_aggregate.py`

聚合规则实现 `check_column`,一次拿整列 `[(row_idx, value), ...]`。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_rules_aggregate.py`:

```python
"""聚合规则:unique / sorted / sorted_desc。check_column 拿整列。"""
from app.rules import REGISTRY


# —— unique ——
def test_unique_ok():
    R = REGISTRY["unique"]()
    col = [(3, 1), (4, 2), (5, 3)]
    assert R.check_column(col, []) == []


def test_unique_duplicate():
    R = REGISTRY["unique"]()
    col = [(3, 1001), (4, 1002), (5, 1001)]  # 1001 重复
    out = R.check_column(col, [])
    assert len(out) == 1
    row_idx, msg = out[0]
    assert row_idx == 5
    assert "1001" in msg
    assert "行 3" in msg


def test_unique_metadata():
    R = REGISTRY["unique"]
    assert R.is_aggregate is True
    assert R.n_params == (0, 0)


# —— sorted ——
def test_sorted_strictly_increasing_ok():
    R = REGISTRY["sorted"]()
    col = [(3, 1), (4, 2), (5, 3)]
    assert R.check_column(col, []) == []


def test_sorted_equal_violation():
    """严格递增,相等也违规。"""
    R = REGISTRY["sorted"]()
    col = [(3, 1), (4, 1)]  # 相等
    out = R.check_column(col, [])
    assert len(out) == 1
    assert out[0][0] == 4


def test_sorted_decrease_violation():
    R = REGISTRY["sorted"]()
    col = [(3, 5), (4, 2)]
    out = R.check_column(col, [])
    assert len(out) == 1
    assert out[0][0] == 4


def test_sorted_single_row_ok():
    R = REGISTRY["sorted"]()
    assert R.check_column([(3, 1)], []) == []


def test_sorted_empty_column_ok():
    R = REGISTRY["sorted"]()
    assert R.check_column([], []) == []


# —— sorted_desc ——
def test_sorted_desc_ok():
    R = REGISTRY["sorted_desc"]()
    col = [(3, 3), (4, 2), (5, 1)]
    assert R.check_column(col, []) == []


def test_sorted_desc_violation():
    R = REGISTRY["sorted_desc"]()
    col = [(3, 1), (4, 2)]  # 递增,违规
    out = R.check_column(col, [])
    assert len(out) == 1
    assert out[0][0] == 4
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_rules_aggregate.py -v`
Expected: FAIL — `KeyError: 'unique'`

- [ ] **Step 3: 在 rules.py 的逐值规则区之后、REGISTRY 之前加聚合规则区**

在 `app/rules.py` 的 `class InRule` 定义**之后**、`# —— 注册表 ——` 之前插入:

```python
# —— 聚合规则 ——


def _skip_empty_for_aggregate(col_values: ColValues) -> list[tuple[int, Any]]:
    """聚合规则跳过空值(None / "" / []),只对有效值判断。

    理由:空值策略 D8 —— 空值由 non_empty 显式管,聚合规则不因空值报错。
    """
    out = []
    for row_idx, val in col_values:
        if val is None:
            continue
        if isinstance(val, str) and val == "":
            continue
        if isinstance(val, list) and len(val) == 0:
            continue
        out.append((row_idx, val))
    return out


class UniqueRule(Rule):
    name = "unique"
    applicable_types = set()  # 任意标量(数组作为整体值参与)
    is_aggregate = True
    n_params = (0, 0)

    def validate_params(self, params: list[str]) -> str | None:
        return None

    def check_column(self, col_values: ColValues, params: list[str]) -> list[tuple[int, str]]:
        seen: dict[Any, int] = {}  # value -> 首次出现行号
        out: list[tuple[int, str]] = []
        for row_idx, val in _skip_empty_for_aggregate(col_values):
            # 数组用 tuple 做 key(list 不可哈希)
            key = tuple(val) if isinstance(val, list) else val
            if key in seen:
                out.append((row_idx, f"值 {val!r} 与行 {seen[key]} 重复"))
            else:
                seen[key] = row_idx
        return out


class SortedRule(Rule):
    name = "sorted"
    applicable_types = {T_INT, T_FLOAT}
    is_aggregate = True
    n_params = (0, 0)

    def validate_params(self, params: list[str]) -> str | None:
        return None

    def check_column(self, col_values: ColValues, params: list[str]) -> list[tuple[int, str]]:
        vals = _skip_empty_for_aggregate(col_values)
        out: list[tuple[int, str]] = []
        for i in range(1, len(vals)):
            prev_row, prev_val = vals[i - 1]
            cur_row, cur_val = vals[i]
            if not (cur_val > prev_val):  # 严格递增:必须 >
                out.append((cur_row, f"值 {cur_val!r} 未严格大于上一行值 {prev_val!r}(行 {prev_row})"))
        return out


class SortedDescRule(Rule):
    name = "sorted_desc"
    applicable_types = {T_INT, T_FLOAT}
    is_aggregate = True
    n_params = (0, 0)

    def validate_params(self, params: list[str]) -> str | None:
        return None

    def check_column(self, col_values: ColValues, params: list[str]) -> list[tuple[int, str]]:
        vals = _skip_empty_for_aggregate(col_values)
        out: list[tuple[int, str]] = []
        for i in range(1, len(vals)):
            prev_row, prev_val = vals[i - 1]
            cur_row, cur_val = vals[i]
            if not (cur_val < prev_val):
                out.append((cur_row, f"值 {cur_val!r} 未严格小于上一行值 {prev_val!r}(行 {prev_row})"))
        return out
```

- [ ] **Step 4: 注册聚合规则**

`app/rules.py` 的 `REGISTRY` 最终形态:

```python
REGISTRY: dict[str, type[Rule]] = {
    # 逐值
    "non_empty": NonEmptyRule,
    "range": RangeRule,
    "elem_range": ElemRangeRule,
    "len": LenRule,
    "regex": RegexRule,
    "in": InRule,
    # 聚合
    "unique": UniqueRule,
    "sorted": SortedRule,
    "sorted_desc": SortedDescRule,
}
```

- [ ] **Step 5: 运行聚合规则测试**

Run: `pytest tests/test_rules_aggregate.py -v`
Expected: all passed

- [ ] **Step 6: 跑全部 rules 测试确认 9 条规则齐全**

Run: `pytest tests/test_rules_registry.py tests/test_rules_per_value.py tests/test_rules_per_value2.py tests/test_rules_aggregate.py -v`
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add app/rules.py tests/test_rules_aggregate.py
git commit -m "feat(rules): 聚合规则 unique / sorted / sorted_desc"
```

---

## Task 6:checker 接入规则调度(含 L2 回显、L3 类型守卫、空值跳过)

**Files:**
- Modify: `app/checker.py`(`check_table` 函数末尾加规则调度)
- Test: `tests/test_checker_rules.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_checker_rules.py`:

```python
"""checker 调度规则:L2 回显、L3 类型守卫、空值跳过、聚合定位、逐值定位。"""
from app import checker
from app.schema import FieldDef, FieldRule, T_INT, T_STRING, T_INT_ARRAY

from tests.conftest import make_field, make_schema


def _errors(rep):
    return [(i.row, i.col, i.message) for i in rep.issues if i.level == checker.LEVEL_ERROR]


# —— L2 回显:规则解析期错误 ——
def test_l2_parse_error_echoed():
    f = make_field("hp", T_INT, rules=[FieldRule(name="range", params=["1"], parse_errors=["参数个数错误"])])
    s = make_schema(fields=[f], rows=[(2, [50])])
    rep = checker.check_table(s)
    errs = _errors(rep)
    assert any("参数个数错误" in m for (_, _, m) in errs)
    assert any(c == "hp" for (_, c, _) in errs)


# —— L3 类型守卫 ——
def test_l3_regex_on_int_errors():
    f = make_field("id", T_INT, rules=[FieldRule(name="regex", params=[r"\d+"], parse_errors=[])])
    s = make_schema(fields=[f], rows=[(2, [123])])
    rep = checker.check_table(s)
    errs = _errors(rep)
    assert any("regex" in m and "int" in m for (_, _, m) in errs)


def test_l3_range_on_string_errors():
    f = make_field("name", T_STRING, rules=[FieldRule(name="range", params=["0", "10"], parse_errors=[])])
    s = make_schema(fields=[f], rows=[(2, ["abc"])])
    rep = checker.check_table(s)
    errs = _errors(rep)
    assert any("range" in m and "string" in m for (_, _, m) in errs)


# —— 逐值规则:定位到行 ——
def test_per_value_range_violation_located():
    f = make_field("hp", T_INT, rules=[FieldRule(name="range", params=["0", "99999"], parse_errors=[])])
    s = make_schema(fields=[f], rows=[(2, [50]), (3, [-1]), (4, [60])])
    rep = checker.check_table(s)
    errs = _errors(rep)
    # 只有行 3 违规
    assert any(r == 3 and c == "hp" for (r, c, _) in errs)
    assert not any(r == 2 for (r, _, _) in errs)


# —— 空值跳过策略 ——
def test_empty_value_skipped_by_range():
    """hp 留空(reader 置 None),range 不报(由 non_empty 管)。"""
    f = make_field("hp", T_INT, rules=[FieldRule(name="range", params=["0", "99999"], parse_errors=[])])
    s = make_schema(fields=[f], rows=[(2, [None])])
    rep = checker.check_table(s)
    errs = _errors(rep)
    assert not any("range" in m for (_, _, m) in errs)


def test_non_empty_catches_empty():
    f = make_field("hp", T_INT, rules=[FieldRule(name="non_empty", params=[], parse_errors=[])])
    s = make_schema(fields=[f], rows=[(2, [None])])
    rep = checker.check_table(s)
    errs = _errors(rep)
    assert any(r == 2 and "空" in m for (r, _, m) in errs)


# —— 聚合规则:定位到冲突行 ——
def test_aggregate_unique_located():
    f = make_field("id", T_INT, rules=[FieldRule(name="unique", params=[], parse_errors=[])])
    s = make_schema(fields=[f], rows=[(2, [1001]), (3, [1002]), (4, [1001])])
    rep = checker.check_table(s)
    errs = _errors(rep)
    assert any(r == 4 and c == "id" for (r, c, _) in errs)


# —— 无规则字段不受影响 ——
def test_no_rules_unchanged():
    f = make_field("hp", T_INT)
    s = make_schema(fields=[f], rows=[(2, [50])])
    rep = checker.check_table(s)
    assert rep.ok
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_checker_rules.py -v`
Expected: FAIL — 规则未生效(`test_l2_parse_error_echoed` 等找不到违规)

- [ ] **Step 3: 在 checker.py 顶部加 import**

`app/checker.py` 现有 import 段(`from . import schema as S` 之后)加:

```python
from . import rules as R
```

- [ ] **Step 4: 在 check_table 末尾加规则调度**

`app/checker.py` 的 `check_table` 函数,**在现有数据行检查循环之后、`if rep.error_count == 0:` 之前**,插入规则调度块。

定位锚点:找到这两行(在函数末尾):

```python
            # 必填/空数组提示
            if fdef.is_array and isinstance(raw, list) and len(raw) == 0:
                add(LEVEL_WARNING, f"字段 {fdef.name!r} 为空数组", row=drow.row_index, col=fdef.name)

    if rep.error_count == 0:
```

在 `    if rep.error_count == 0:` **之前**插入:

```python
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

```

- [ ] **Step 5: 加 _is_rule_empty 辅助函数**

在 `app/checker.py` 的 `check_table` 函数**之前**(模块级,`_IDENT_RE` 定义附近)加:

```python
def _is_rule_empty(value: Any) -> bool:
    """规则校验的空值判定:None / 空串 / 空数组视为空(由 non_empty 管)。"""
    if value is None:
        return True
    if isinstance(value, str) and value == "":
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    return False
```

- [ ] **Step 6: 运行测试**

Run: `pytest tests/test_checker_rules.py -v`
Expected: all passed

- [ ] **Step 7: 跑全量回归确认现有 checker 行为没破**

Run: `python -c "from app import checker, schema; from tests.conftest import make_schema, make_field; s=make_schema(fields=[make_field('id',1)], rows=[(2,[1])]); print(checker.check_table(s).ok)"`
Expected: 输出 `True`

- [ ] **Step 8: Commit**

```bash
git add app/checker.py tests/test_checker_rules.py
git commit -m "feat(checker): 接入 #rule 规则调度(L2 回显/L3 守卫/空值跳过/聚合定位)"
```

---

## Task 7:excel_reader 识别 `#rule` 行(累加/去重/稀疏/sep/两层切分)

**Files:**
- Modify: `app/excel_reader.py`
- Test: `tests/test_excel_reader_rules.py`

reader 的改动分两块:(1) A 列标记识别 `#rule[sep=...]`;(2) 字段构造阶段把规则填进 `FieldDef.rules`。

- [ ] **Step 1: 写失败测试(用真实 .xlsx 文件)**

创建 `tests/test_excel_reader_rules.py`:

```python
"""excel_reader 识别 #rule 行:多行累加、去重、稀疏、sep 配置、两层切分、L1 sep 冲突。"""
import openpyxl
from pathlib import Path

from app import excel_reader
from app.schema import T_INT, T_STRING

TMP = Path(__file__).parent / "_tmp_rules.xlsx"


def _write(ws_rows):
    """ws_rows: list of row tuples;每行第一个元素是 A 列标记(或 None)。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in ws_rows:
        ws.append(r)
    wb.save(TMP)
    wb.close()
    return TMP


def _cleanup():
    if TMP.exists():
        TMP.unlink()


def test_basic_rule_row_parsed():
    try:
        _write([
            ("##", "int", "string"),
            ("#name", "id", "name"),
            ("#rule", "unique", "non_empty"),
            ("", 1, "a"),
        ])
        s = excel_reader.read_table(TMP)
        assert len(s.fields) == 2
        assert s.fields[0].name == "id"
        assert len(s.fields[0].rules) == 1
        assert s.fields[0].rules[0].name == "unique"
        assert s.fields[1].rules[0].name == "non_empty"
        assert s.rule_sep == ";"  # 默认
    finally:
        _cleanup()


def test_multi_rule_in_cell_split_by_default_sep():
    try:
        _write([
            ("##", "int"),
            ("#name", "hp"),
            ("#rule", "range:0,99999; non_empty"),
            ("", 50),
        ])
        s = excel_reader.read_table(TMP)
        rules = s.fields[0].rules
        assert [r.name for r in rules] == ["range", "non_empty"]
        assert rules[0].params == ["0", "99999"]
    finally:
        _cleanup()


def test_custom_sep():
    try:
        _write([
            ("##", "int"),
            ("#name", "hp"),
            ("#rule[sep=##]", "range:0,99999##non_empty"),
            ("", 50),
        ])
        s = excel_reader.read_table(TMP)
        assert [r.name for r in s.fields[0].rules] == ["range", "non_empty"]
        assert s.rule_sep == "##"
    finally:
        _cleanup()


def test_multiple_rule_rows_accumulate():
    try:
        _write([
            ("##", "int"),
            ("#name", "id"),
            ("#rule", "unique", None),       # 第一行:id 有规则,name 列空
            ("#rule", "sorted", None),       # 第二行:累加到 id
            ("", 1),
        ])
        s = excel_reader.read_table(TMP)
        assert [r.name for r in s.fields[0].rules] == ["unique", "sorted"]
    finally:
        _cleanup()


def test_sparse_rule_row():
    """第二行 #rule 只给某列,name 列空。"""
    try:
        _write([
            ("##", "int", "string"),
            ("#name", "id", "name"),
            ("#rule", "unique", "non_empty"),
            ("#rule", "sorted", None),       # 只 id 有,name 跳过
            ("", 1, "a"),
        ])
        s = excel_reader.read_table(TMP)
        assert [r.name for r in s.fields[0].rules] == ["unique", "sorted"]
        assert [r.name for r in s.fields[1].rules] == ["non_empty"]  # 只有一条
    finally:
        _cleanup()


def test_dedup_same_rule():
    try:
        _write([
            ("##", "int"),
            ("#name", "id"),
            ("#rule", "unique; unique"),     # 重复
            ("", 1),
        ])
        s = excel_reader.read_table(TMP)
        assert len(s.fields[0].rules) == 1
    finally:
        _cleanup()


def test_duplicate_rule_row_not_reported_as_error():
    """多个 #rule 行不应触发"重复定义行"错误(现有 reader 对其它标记会报)。"""
    try:
        _write([
            ("##", "int"),
            ("#name", "id"),
            ("#rule", "unique"),
            ("#rule", "sorted"),
            ("", 1),
        ])
        s = excel_reader.read_table(TMP)
        # 不应有 #rule 重复定义的 parse_error
        assert not any("重复" in e and "#rule" in e for e in s.parse_errors)
    finally:
        _cleanup()


def test_l1_sep_conflict_with_comma_errors():
    """sep=, 与参数分隔符冲突,报 L1 错。"""
    try:
        _write([
            ("##", "int"),
            ("#name", "hp"),
            ("#rule[sep=,]", "range:0,99999"),
            ("", 50),
        ])
        s = excel_reader.read_table(TMP)
        assert any("sep" in e and "," in e for e in s.parse_errors)
    finally:
        _cleanup()


def test_empty_rule_cell_skipped():
    """整行 #rule 但单元格全空:不报错。"""
    try:
        _write([
            ("##", "int"),
            ("#name", "id"),
            ("#rule", None),
            ("", 1),
        ])
        s = excel_reader.read_table(TMP)
        assert s.fields[0].rules == []
        assert s.parse_errors == []
    finally:
        _cleanup()


def test_rule_row_must_not_break_existing_marks():
    """有 #rule 时,其它定义行仍正常解析。"""
    try:
        _write([
            ("##", "int", "string"),
            ("#name", "id", "name"),
            ("#desc", "主键", "名字"),
            ("#cs", "both", "client"),
            ("#rule", "unique", None),
            ("", 1, "a"),
        ])
        s = excel_reader.read_table(TMP)
        assert s.fields[0].desc == "主键"
        assert s.fields[1].side == "client"
        assert s.fields[0].rules[0].name == "unique"
    finally:
        _cleanup()
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_excel_reader_rules.py -v`
Expected: FAIL — `#rule` 行被当成未识别标记,`s.rule_sep` 不存在或规则不填充

- [ ] **Step 3: 在 excel_reader.py 加 #rule 标记识别**

修改 `app/excel_reader.py` 顶部标记常量区:

```python
# A 列行类型标记
MARK_TYPE = "##"
MARK_NAME = "#name"
MARK_DESC = "#desc"
MARK_CS = "#cs"
# #rule 可带 sep 配置:#rule 或 #rule[sep=...];用前缀匹配识别
MARK_RULE_PREFIX = "#rule"

# #rule[sep=...] 解析正则:group1 = sep 内容
_RULE_MARK_RE = re.compile(r"^#rule(?:\[\s*sep\s*=\s*(.*?)\s*\])?$")
```

更新 `_KNOWN_MARKS`(保留用于"已知标记"判断,但 `#rule` 因带后缀需特殊处理):

```python
_KNOWN_MARKS = (MARK_TYPE, MARK_NAME, MARK_DESC, MARK_CS)
```

- [ ] **Step 4: 改 reader 主循环识别 #rule 行**

修改 `app/excel_reader.py` 的 `read_table` 主循环。当前逻辑(`excel_reader.py:157-184`)对 A 列字符串先判 `in _KNOWN_MARKS`,否则报"未识别"。

替换 A 列分支判断逻辑。找到这段:

```python
        a = row[0]
        a_str = "" if a is None else str(a).strip()
        if a_str == "":
            # 数据行
            data_rows_raw.append((excel_row, row))
            continue
        if a_str in _KNOWN_MARKS:
            if a_str in seen_marks:
                schema.parse_errors.append(
                    f"行 {excel_row}: 重复的 {a_str} 定义行(首次出现于行 {seen_marks[a_str]})"
                )
            seen_marks[a_str] = excel_row
            if a_str == MARK_TYPE:
                type_row = row
            elif a_str == MARK_NAME:
                name_row = row
            elif a_str == MARK_DESC:
                desc_row = row
            else:  # MARK_CS
                cs_row = row
        else:
            schema.parse_errors.append(
                f"行 {excel_row}: A 列标记 {a_str!r} 未识别,该行被忽略"
            )
```

替换为(增加 `#rule` 分支,且 `#rule` 不走"重复定义"检查):

```python
        a = row[0]
        a_str = "" if a is None else str(a).strip()
        if a_str == "":
            # 数据行
            data_rows_raw.append((excel_row, row))
            continue
        # #rule 行(可带 [sep=...])
        rule_m = _RULE_MARK_RE.match(a_str) if a_str.startswith(MARK_RULE_PREFIX) else None
        if rule_m is not None:
            # 解析 sep 配置
            sep_raw = rule_m.group(1)
            if sep_raw is not None:
                if sep_raw == "":
                    schema.parse_errors.append(f"行 {excel_row}: #rule[sep=] 的 sep 为空")
                elif sep_raw == ",":
                    schema.parse_errors.append(
                        f"行 {excel_row}: #rule 的 sep 不能是 ','(与规则参数分隔符冲突)"
                    )
                elif schema.rule_sep == ";" and not rule_rows:
                    # 首次出现 sep 配置,采纳
                    schema.rule_sep = sep_raw
                elif sep_raw != schema.rule_sep:
                    schema.parse_errors.append(
                        f"行 {excel_row}: #rule 的 sep 配置 {sep_raw!r} 与首次 {schema.rule_sep!r} 不一致,已忽略"
                    )
            rule_rows.append((excel_row, row))
            continue
        if a_str in _KNOWN_MARKS:
            if a_str in seen_marks:
                schema.parse_errors.append(
                    f"行 {excel_row}: 重复的 {a_str} 定义行(首次出现于行 {seen_marks[a_str]})"
                )
            seen_marks[a_str] = excel_row
            if a_str == MARK_TYPE:
                type_row = row
            elif a_str == MARK_NAME:
                name_row = row
            elif a_str == MARK_DESC:
                desc_row = row
            else:  # MARK_CS
                cs_row = row
        else:
            schema.parse_errors.append(
                f"行 {excel_row}: A 列标记 {a_str!r} 未识别,该行被忽略"
            )
```

并在 `data_rows_raw` 初始化旁边,加 `rule_rows` 初始化。找到:

```python
    data_rows_raw: list[tuple[int, tuple]] = []
```

在其后加:

```python
    rule_rows: list[tuple[int, tuple]] = []  # [(excel_row, row), ...] —— #rule 行(可能多行)
```

- [ ] **Step 5: 在字段构造阶段填充 rules**

修改 `app/excel_reader.py`,在字段构造循环**之后**(`schema.fields.append(...)` 那段之后,`if not schema.fields:` 检查**之前**),插入规则填充。

定位:找到构造字段的 for 循环结束处。在 `# 缺失字段定义的列...` 注释之前插入:

```python
    # —— 填充 #rule 规则(多行累加、稀疏、去重)——
    # 复用 type_cells 的列对齐:#rule 行 B 列对应 fields[0],C 列对应 fields[1]...
    field_indices = _build_field_indices(type_cells)  # 注意:后面会再算一次,这里提前算了无妨
    _apply_rule_rows(schema, rule_rows, field_indices, type_cells)
```

并删除刚才循环末尾前那句注释里重复的 `field_indices = _build_field_indices(type_cells)`(它在原代码约 250 行处,本次插在它之前会重复定义,所以要把原来那行的位置调整:把它移到 `_apply_rule_rows` 调用前,函数末尾的循环复用此变量)。

**实际操作**:把原代码里这一行:

```python
    # 注意:数据行列数与字段数可能不一致(因为有的列类型解析失败被跳过)
    # 这里按 fields 的"原始列下标"读取。fields 的顺序与 type 行一致,
    # 但跳过了 parse 失败的列 —— 为稳健起见,建立 fields 原始列下标映射。
    field_indices = _build_field_indices(type_cells)
```

**移到** `_apply_rule_rows` 调用之前(即上面插入点),让 `field_indices` 在规则填充和数据行解析两处共用。最终该段形如:

```python
    # —— 填充 #rule 规则(多行累加、稀疏、去重)——
    # 建立 fields[i] -> 原始列下标(B 列=1)映射,规则填充与数据行解析共用
    field_indices = _build_field_indices(type_cells)
    _apply_rule_rows(schema, rule_rows, field_indices, type_cells)
```

- [ ] **Step 6: 加 _apply_rule_rows 辅助函数**

在 `app/excel_reader.py` 的 `_build_field_indices` 函数**之后**,加:

```python
def _apply_rule_rows(
    schema: TableSchema,
    rule_rows: list[tuple[int, tuple]],
    field_indices: dict[int, int],
    type_cells: list,
) -> None:
    """把 #rule 行的单元格规则累加进对应 FieldDef.rules。

    - 多行累加;空单元格跳过(稀疏)
    - 按 (name, tuple(params)) 去重,保留首次顺序
    - 单元格用 schema.rule_sep 切分多规则;每段 parse_rule 解析
    """
    from . import rules as R  # 延迟导入,避免循环依赖

    for excel_row, row in rule_rows:
        # 字段区从 B 列(index=1)开始;对齐到 fields 的原始列下标
        cells = list(row[1:]) if len(row) > 1 else []
        # 建立 列下标(B=1) -> field 索引 的反查表
        col_to_field: dict[int, int] = {col: fi for fi, col in field_indices.items()}
        for col_idx in range(1, len(cells) + 1):
            cell = cells[col_idx - 1]
            if cell is None or str(cell).strip() == "":
                continue  # 稀疏:空单元格跳过
            fi = col_to_field.get(col_idx)
            if fi is None or fi >= len(schema.fields):
                continue  # 该列无对应字段(类型解析失败被跳过)
            fdef = schema.fields[fi]
            text = str(cell).strip()
            # 第1层切分:rule_sep 切多规则
            segments = text.split(schema.rule_sep)
            for seg in segments:
                seg = seg.strip()
                if seg == "":
                    continue  # 残留空段跳过
                fr = R.parse_rule(seg)
                if fr is None:
                    continue
                # 去重:按 (name, tuple(params))
                key = (fr.name, tuple(fr.params))
                if any((r.name, tuple(r.params)) == key for r in fdef.rules):
                    continue
                fdef.rules.append(fr)
```

- [ ] **Step 7: 运行 reader 测试**

Run: `pytest tests/test_excel_reader_rules.py -v`
Expected: all passed

- [ ] **Step 8: 跑全量测试确认无回归**

Run: `pytest tests/ -v`
Expected: all passed(含 Task 1–6 的测试)

- [ ] **Step 9: Commit**

```bash
git add app/excel_reader.py tests/test_excel_reader_rules.py
git commit -m "feat(reader): 识别 #rule 行(累加/去重/稀疏/sep 配置/两层切分/L1 冲突检测)"
```

---

## Task 8:样例表 + 端到端集成验证

**Files:**
- Create: `sample/ItemRules.xlsx`(用脚本生成)
- Create: `tests/test_integration_rules.py`

- [ ] **Step 1: 写集成测试(验证违规阻断、通过可构建)**

创建 `tests/test_integration_rules.py`:

```python
"""端到端:带 #rule 的样例表 → scan → check → build。
违规表阻断导出;合规表正常产出。
"""
from pathlib import Path

import openpyxl

from app import checker, excel_reader

SAMPLE = Path(__file__).parent.parent / "sample" / "ItemRules.xlsx"
TMP_BAD = Path(__file__).parent / "_tmp_bad.xlsx"
TMP_GOOD = Path(__file__).parent / "_tmp_good.xlsx"


def _make(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    wb.save(path)
    wb.close()


GOOD_TABLE = [
    ("##", "int", "string", "int", "int[sep=|]"),
    ("#name", "id", "name", "hp", "dropList"),
    ("#desc", "主键", "名字", "血量", "掉落"),
    ("#cs", "both", "both", "server", "client"),
    ("#rule[sep=;]", "unique; sorted; range:1000,9999", "non_empty; len:1,20", "range:0,99999", "elem_range:1,9999"),
    ("", 1001, "木剑", 50, "1001|1002"),
    ("", 1002, "铁剑", 80, "1003"),
    ("", 1003, "神剑", 99999, "1001|1004|1005"),
]


def test_good_table_passes_check():
    try:
        _make(TMP_GOOD, GOOD_TABLE)
        s = excel_reader.read_table(TMP_GOOD)
        rep = checker.check_table(s)
        assert rep.ok, [i.message for i in rep.issues if i.level == "ERROR"]
    finally:
        if TMP_GOOD.exists():
            TMP_GOOD.unlink()


def test_bad_table_blocked_by_range():
    bad = list(GOOD_TABLE)
    # 把第二行数据 hp 改成 -1(违反 range:0,99999)
    bad[6] = ("", 1002, "铁剑", -1, "1003")
    try:
        _make(TMP_BAD, bad)
        s = excel_reader.read_table(TMP_BAD)
        rep = checker.check_table(s)
        assert not rep.ok
        assert any("range" in i.message and "hp" in i.message for i in rep.issues if i.level == "ERROR")
    finally:
        if TMP_BAD.exists():
            TMP_BAD.unlink()


def test_bad_table_blocked_by_duplicate_id():
    bad = list(GOOD_TABLE)
    # id 重复
    bad[6] = ("", 1001, "铁剑", 80, "1003")  # 1001 与第一行重复
    try:
        _make(TMP_BAD, bad)
        s = excel_reader.read_table(TMP_BAD)
        rep = checker.check_table(s)
        # 注意:id 既是主键(内置唯一)又配了 unique 规则;两者都会报
        assert not rep.ok
    finally:
        if TMP_BAD.exists():
            TMP_BAD.unlink()


def test_bad_table_blocked_by_sort():
    bad = list(GOOD_TABLE)
    # id 不递增:把第三行 id 改小
    bad[7] = ("", 1000, "神剑", 99999, "1001|1004|1005")
    try:
        _make(TMP_BAD, bad)
        s = excel_reader.read_table(TMP_BAD)
        rep = checker.check_table(s)
        assert not rep.ok
        assert any("sorted" in i.message for i in rep.issues if i.level == "ERROR")
    finally:
        if TMP_BAD.exists():
            TMP_BAD.unlink()


def test_sample_itemrules_file_exists_and_valid():
    """仓库自带的 sample/ItemRules.xlsx 能正常解析。"""
    if not SAMPLE.exists():
        # 样例表由 Step 3 生成;若还没生成,这里跳过(Step 3 会保证)
        import pytest
        pytest.skip("sample/ItemRules.xlsx 尚未生成")
    s = excel_reader.read_table(SAMPLE)
    rep = checker.check_table(s)
    assert rep.ok, [i.message for i in rep.issues if i.level == "ERROR"]
```

- [ ] **Step 2: 运行(部分应通过,sample 文件测试跳过)**

Run: `pytest tests/test_integration_rules.py -v`
Expected: 前 4 个通过,`test_sample_itemrules_file_exists_and_valid` skipped

- [ ] **Step 3: 生成 sample/ItemRules.xlsx**

Run(脚本内联,用 python 生成):

```bash
python -c "
import openpyxl
from pathlib import Path
wb = openpyxl.Workbook()
ws = wb.active
rows = [
    ('##', 'int', 'string', 'int', 'int[sep=|]'),
    ('#name', 'id', 'name', 'hp', 'dropList'),
    ('#desc', '主键', '名字', '血量', '掉落'),
    ('#cs', 'both', 'both', 'server', 'client'),
    ('#rule[sep=;]', 'unique; sorted; range:1000,9999', 'non_empty; len:1,20', 'range:0,99999', 'elem_range:1,9999'),
    ('', 1001, '木剑', 50, '1001|1002'),
    ('', 1002, '铁剑', 80, '1003'),
    ('', 1003, '神剑', 99999, '1001|1004|1005'),
]
for r in rows:
    ws.append(r)
out = Path('sample/ItemRules.xlsx')
wb.save(out)
wb.close()
print('written', out.resolve())
"
```
Expected: 输出 `written .../sample/ItemRules.xlsx`

- [ ] **Step 4: 再次运行集成测试**

Run: `pytest tests/test_integration_rules.py -v`
Expected: all passed(含 sample 文件测试)

- [ ] **Step 5: 手动启动服务验证网页展示**

Run: `python run.py`,浏览器打开 `http://127.0.0.1:9900`,在路径配置里 input_dir 指向 `sample` 目录,点「扫描表」,确认:
- `ItemRules` 表出现在列表,校验状态 OK
- issues 列表无 ERROR

(此为手动验证步骤,无需自动化;若不便启动,执行 `python -c "from app.main import app; print('app imports ok')"` 确认无导入错误即可)

- [ ] **Step 6: Commit**

```bash
git add sample/ItemRules.xlsx tests/test_integration_rules.py
git commit -m "test: #rule 端到端集成测试 + sample/ItemRules.xlsx 样例表"
```

---

## Task 9:更新 README 文档

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 在「表格式规范」的 A 列标记表里加 `#rule` 行**

找到 README 里这张表:

```
| A 列 | 含义 |
|------|------|
| `##` | 字段类型行 |
| `#name` | 字段名行(代码用标识符) |
| `#desc` | 字段说明行(注释) |
| `#cs` | 归属行:`both` / `client` / `server` |
| *(空)* | 数据行 |
```

在 `#cs` 行之后加一行:

```
| `#rule` | 字段规则行(可选,可多行);详见下方「自定义校验规则」 |
```

- [ ] **Step 2: 在「校验规则」章节之前,新增「自定义校验规则」小节**

找到 `## 校验规则` 标题,**在其之前**插入新小节:

```markdown
## 自定义校验规则(可选)

在表里加 `#rule` 定义行,可对**单个字段跨所有行**声明领域约束,校验不过即阻断导出。规则行可写多行(累加),也可留空单元格(只约束部分字段)。

**示例**

| A | B(id) | C(name) | D(hp) | E(dropList) |
|---|-------|---------|-------|-------------|
| `##` | int | string | int | int[sep=\|] |
| `#name` | id | name | hp | dropList |
| `#rule[sep=;]` | unique; sorted | non_empty; len:1,20 | range:0,99999 | elem_range:1,9999 |
| `#rule` | range:1000,9999 | | | |
|  | 1001 | 木剑 | 50 | 1001\|1002 |

**语法**

- 多条规则默认用 `;` 分隔;可在 A 列写 `#rule[sep=##]` 改分隔符(`,` 不允许,与参数分隔符冲突)
- 单条规则:`规则名` 或 `规则名:参数1,参数2`
- 范围参数支持 `*` 表示不限:`range:0,*` = 只设下界

**内置规则**

| 规则 | 参数 | 适用类型 | 作用 |
|------|------|---------|------|
| `unique` | — | 任意标量 | 所有值唯一 |
| `sorted` / `sorted_desc` | — | int/float | 严格递增 / 递减 |
| `non_empty` | — | 任意 | 非空(空串/空数组视为空) |
| `range` | `min,max` | int/float | 值在 [min,max] 内 |
| `len` | `min,max` | 数组 | 数组长度在 [min,max] 内 |
| `elem_range` | `min,max` | int[]/float[] | 每个元素在 [min,max] 内 |
| `regex` | `PATTERN` | string | 正则全匹配 |
| `in` | `a,b,c` | 任意标量 | 值在枚举集合内 |

> 空值(空串/空数组)默认**不触发**逐值规则,由 `non_empty` 显式管空。主键为空仍按 ERROR 处理(内置)。
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README 增加 #rule 自定义校验规则说明"
```

---

## 验收清单

完成所有 Task 后,执行最终验证:

- [ ] **全量测试通过**

Run: `pytest tests/ -v`
Expected: all passed,无 skip(除环境相关)

- [ ] **sample 表手动构建成功**

Run: `python run.py`,网页 input_dir 指向 `sample`,「扫描表」→ 确认 `Item` 和 `ItemRules` 都 OK →「全部构建」→ 确认 `out/` 产出 `.bytes` 与代码

- [ ] **违规阻断验证**

临时改 `sample/ItemRules.xlsx` 某行 hp 为 -1,「扫描表」应看到 ERROR,「全部构建」应被阻断

- [ ] **代码结构核查**

- `app/rules.py` 是独立模块,Rule 基类 + 9 子类 + REGISTRY
- 加新规则只需:新增子类 + REGISTRY 注册一行(checker 不改)—— 可读 `app/rules.py` 顶部 docstring 确认

## Self-Review 结果(plan 写完后的自查)

**1. Spec 覆盖**:
- 第 3 章规则集 9 条 → Task 3/4/5 全覆盖
- 第 4 章表格式 `#rule[sep=]` → Task 7
- 第 5 章架构(rules.py/FieldDef/reader/checker)→ Task 1/2/7/6
- 第 6 章解析与数据流 → Task 7(解析)+ Task 6(校验)
- 第 7 章报错格式 → Task 6(checker 的 add 调用句式)
- 第 8 章网页展示 → Task 8 Step 5 手动验证(零改动,符合 spec)
- 第 9 章边界清单 → 散布在各 Task 测试中(空值跳过 Task 6、空段残留 Task 7、主键重复 unique Task 3/8 等)
- 第 10 章测试策略 → Task 0/3/4/5/6/7/8 全覆盖

**2. 占位符扫描**:无 TBD/TODO;每个 Step 含具体代码或命令。

**3. 类型一致性**:
- `FieldRule(name, params, parse_errors)` 在 Task 1 定义,Task 2/6/7 使用一致
- `Rule.check_value(value, params) -> str|None` / `check_column(col_values, params) -> list[(row_idx,msg)]` 签名在 Task 2 定义,Task 3/4/5 实现、Task 6 调用一致
- `REGISTRY: dict[str, type[Rule]]` 在 Task 2 定义,逐 Task 填充
- `_is_rule_empty`(Task 6)与 `_skip_empty_for_aggregate`(Task 5)语义一致(都判 None/""/[]),分别放 checker 和 rules 是因作用域不同,不冲突

无遗留问题。
