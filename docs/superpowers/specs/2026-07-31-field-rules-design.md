# 设计:表字段自定义检查规则(单字段整列规则)

- **日期**:2026-07-31
- **状态**:已通过设计评审,待实现
- **作用域**:规则类型 B —— 单字段整列规则(某字段跨所有行)
- **不包含**:跨字段(单行内多字段关系)、跨表(主外键引用完整性)—— 留待后续扩展

## 1. 背景与目标

TableAssembly 现有校验只覆盖通用项(类型转换、主键唯一/非空、必填、空数组)。策划对具体字段常有领域约束需求,如:

- `hp` 必须 ∈ [0, 99999]
- `name` 长度 1–20、非空
- `dropList` 每个元素 ∈ [1, 9999]、数组长度 ≥ 1
- `id` 严格递增

这些约束目前只能靠人眼或事后脚本,无法在导出链路强制。本设计引入**用户可写的字段级规则**,在 checker 阶段强制执行,违规即阻断导出(与现有 ERROR 同语义)。

## 2. 关键决策(均已确认)

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| D1 | 作用域 | 单字段整列(类型 B) | 最常见、最规整;跨字段/跨表后续按同模式扩展 |
| D2 | 规则位置 | 写在 Excel 里,新增 `#rule` 定义行 | 与 `##`/`#name`/`#cs`/`#desc` 同构,自包含,随表 git |
| D3 | 单条规则语法 | 声明式规则名 + 参数 | 安全(无 eval)、可读、契合"整列"语义 |
| D4 | 多条规则分隔 | `#rule[sep=;]` 可配,默认 `;` | 与 `## int[sep=\|]` 对称,零学习成本 |
| D5 | 多行 `#rule` | 累加语义(不覆盖、不报重复行) | 规则多时分行写,可读性好 |
| D6 | 稀疏支持 | `#rule` 行空单元格 = 该字段此行无规则 | 规则多的字段单独多写几行,别的列空着 |
| D7 | 去重 | 按 `(name, tuple(params))` 去重,保留首次顺序 | 容忍策划复制粘贴,不报错 |
| D8 | 空值策略 | 逐值规则遇空值跳过,由 `non_empty` 显式管空 | 可选字段允许空;主键空已内置 ERROR |
| D9 | 规则级别 | 统一 ERROR(无 WARNING 级别) | 工具定位是"硬闸门";弱提示留给内置项 |
| D10 | 架构 | 新增 `app/rules.py`,Rule 抽象基类 + REGISTRY | 对齐 codegen 扩展模式,可独立测试 |
| D11 | 诊断复用 | 规则违规走现有 `Issue` 结构 | 网页端零改动即可展示 |

## 3. 内置规则集

每条规则作用于"某字段跨所有行的值"。参数用 `,` 分隔。

| 规则名 | 参数 | 适用类型 | 语义 | 类别 |
|--------|------|---------|------|------|
| `unique` | 无 | 标量 | 所有值唯一(主键已内置,重复定义不报错) | 聚合 |
| `sorted` | 无 | int/float 标量 | 严格递增(aᵢ < aᵢ₊₁) | 聚合 |
| `sorted_desc` | 无 | int/float 标量 | 严格递减 | 聚合 |
| `non_empty` | 无 | 标量/数组 | 标量值非空串/None;数组非空 | 逐值 |
| `range` | `min,max` | int/float 标量 | 值 ∈ [min, max];`*` 表示不限 | 逐值 |
| `len` | `min,max` | 数组 | 数组长度 ∈ [min, max];`*` 同上 | 逐值 |
| `elem_range` | `min,max` | 数组(int/float) | 每个元素 ∈ [min, max] | 逐值 |
| `regex` | `PATTERN` | string 标量 | 正则全匹配(`re.fullmatch`) | 逐值 |
| `in` | `a,b,c` | 标量 | 值在枚举集合内;空值不触发 | 逐值 |

**参数通配 `*`**:`range:0,*` = 只设下界;`range:*,100` = 只设上界;`range:*,*` 解析期报错(无意义)。

**类别说明**:逐值规则(per-value)逐个值判断;聚合规则(aggregate)一次拿整列值判断。checker 按类别分发,入参不同(单值 vs 整列)。

## 4. 表格式扩展

`#rule` 是新的 A 列定义行,与现有定义行同构。

```
A列            | B(id)                  | C(name)             | D(hp)           | E(dropList)
---------------|------------------------|---------------------|-----------------|------------------
##             | int                    | string              | int             | int[sep=|]
#name          | id                     | name                | hp              | dropList
#desc          | 主键                   | 名字                | 血量            | 掉落
#cs            | both                   | both                | server          | client
#rule[sep=;]   | unique; sorted         | non_empty; len:1,20 | range:0,99999   | elem_range:1,9999
#rule          | range:1000,9999        |                     |                 |
               ↑ 第二行累加到 id        ↑ 空单元格跳过(稀疏)
```

**A 列标记识别**:

| 写法 | 分隔符 |
|------|--------|
| `#rule` | `;`(默认) |
| `#rule[sep=;]` | `;` |
| `#rule[sep=##]` | `##`(多字符支持) |
| `#rule[sep=,]` | **报错**(与参数分隔符 `,` 冲突) |

**两层分隔符**(严格区分,不可打架):

| 层级 | 字符 | 可配 | 用途 |
|------|------|------|------|
| 规则之间 | `;` | 可(`#rule[sep=]`) | 切分多条规则 |
| 规则参数之间 | `,` | **不可** | 切分规则内参数 |

## 5. 架构

### 5.1 模块划分

```
app/
  rules.py          ← 新增:Rule 抽象基类 + 9 个规则子类 + REGISTRY + 解析/校验公共接口
  schema.py         ← 改:FieldDef 加 rules 字段;TableSchema 加 rule_sep
  excel_reader.py   ← 改:识别 #rule 行、填充 FieldDef.rules
  checker.py        ← 改:字段校验循环里调度 rules
  main.py / web     ← 几乎不改:规则违规走现有 Issue 结构
```

### 5.2 数据模型(schema.py)

```python
@dataclass
class FieldRule:
    """解析后的一条规则(可能含解析期错误)。"""
    name: str                 # 规则名,如 "range"
    params: list[str]         # 参数,如 ["0", "99999"];无参数为空
    parse_errors: list[str]   # 解析期问题(规则名未知、参数个数错等),checker 回显

@dataclass
class FieldDef:
    ...  # 现有字段不变
    rules: list[FieldRule] = field(default_factory=list)  # 新增

@dataclass
class TableSchema:
    ...  # 现有字段不变
    rule_sep: str = ";"  # 新增:从 #rule[sep=...] 读
```

`FieldRule` 与 `FieldDef.rules` 进 `to_dict()`,网页可展示字段配置的规则。

### 5.3 规则抽象(app/rules.py)

对齐 codegen 的"抽象基类 + 注册表"扩展模式:

```python
class Rule(ABC):
    """单字段整列规则的抽象基类。每条规则自包含。"""
    name: str
    applicable_types: set[int]        # 适用 type_code;空集 = 任意类型
    is_aggregate: bool = False        # True=聚合(整列),False=逐值
    n_params: tuple[int, int]         # 参数个数范围 [min, max]

    @abstractmethod
    def validate_params(self, params: list[str]) -> str | None: ...

    def check_value(self, value, params) -> str | None: ...        # 逐值规则实现
    def check_column(self, col_values, params) -> list[tuple[int, str]]: ...  # 聚合规则实现

# 具体规则:每条一个类
class UniqueRule(Rule): ...
class SortedRule(Rule): ...
class SortedDescRule(Rule): ...
class NonEmptyRule(Rule): ...
class RangeRule(Rule): ...
class LenRule(Rule): ...
class ElemRangeRule(Rule): ...
class RegexRule(Rule): ...
class InRule(Rule): ...

# 注册表:加规则的唯一入口
REGISTRY: dict[str, type[Rule]] = {
    "unique": UniqueRule, "sorted": SortedRule, "sorted_desc": SortedDescRule,
    "non_empty": NonEmptyRule, "range": RangeRule, "len": LenRule,
    "elem_range": ElemRangeRule, "regex": RegexRule, "in": InRule,
}

# 公共接口
def parse_rule(text: str) -> FieldRule: ...
def check_field_rules(field: FieldDef, col_values) -> list[Issue]: ...
```

### 5.4 可扩展性

| 扩展场景 | 做法 | 改动范围 |
|---------|------|---------|
| 加新规则 | 新增 `XxxRule(Rule)` + REGISTRY 注册一行 | 只动 rules.py |
| 加新作用域(跨字段/跨表) | 新增对应基类 + check 入口;字段级 Rule 不动 | 边界清晰 |
| 规则配置外部化 | 扩展 parse_rule 输入源,Rule 子类全复用 | 单点改动 |

文件拆分时机:9 条规则单文件 `rules.py` 足够(预计 200–300 行)。规则数翻倍或加跨字段作用域时,再拆成 `app/rules/` 包(`base.py` + `per_value.py` + `aggregate.py` + `__init__.py`)。拆分成本极低,因类已自包含。**现在不拆 = YAGNI**。

## 6. 解析与数据流

### 6.1 解析阶段(excel_reader.py)

```
读 Excel
  ├─ 遇到 A 列 = "#rule[sep=...]" 或 "#rule"
  │    ├─ 解析 [sep=...] → schema.rule_sep
  │    │    (多次出现以首次为准;后续重复 sep 配置 → parse_error WARNING)
  │    ├─ 这行不算"重复定义错误"(仅对 #rule 放宽现有 167-172 行约束)
  │    └─ 遍历 B 列起每个单元格:
  │         ├─ 空单元格 → 跳过(稀疏支持)
  │         └─ 非空 → rule_sep 切分 → 每段 parse_rule → 追加到该字段 rules
  └─ 字段构造:按 #name/#cs 列对齐方式,#rule 单元格按列下标对齐到 FieldDef
```

**单元格两层切分**:

```
"non_empty;len:1,20"
  ├─ 第1层 rule_sep ";" → ["non_empty", "len:1,20"]
  └─ 第2层 首个 ":" 切分 → ("len", ["1","20"]) / ("non_empty", [])
       (首个冒号切分,保证 regex:http://... 含冒号 pattern 不被切错)
```

**去重**:同字段规则列表按 `(name, tuple(params))` 去重,保留首次顺序。

**字段未匹配兜底**:`#rule` 单元格对应列在 `##` 行解析失败(无 FieldDef)→ parse_error。

### 6.2 校验阶段(checker.py)

在现有 `check_table` 字段校验循环后,新增规则调度:

```
for fdef in schema.fields:
    rules = fdef.rules

    # L2 回显:解析期规则错误(规则名未知、参数错)
    for r in rules:
        for msg in r.parse_errors:
            add(ERROR, msg, col=fdef.name)

    col_values = [(row.row_index, row.values[fi]) for row in schema.rows]

    # 逐值规则
    for r in rules:
        rule_cls = REGISTRY[r.name]
        if not rule_cls.is_aggregate:
            for row_idx, val in col_values:
                if _is_empty(val) and r.name != "non_empty": continue
                msg = rule_cls.check_value(val, r.params)
                if msg: add(ERROR, msg, row=row_idx, col=fdef.name)

    # 聚合规则
    for r in rules:
        rule_cls = REGISTRY[r.name]
        if rule_cls.is_aggregate:
            for row_idx, msg in rule_cls.check_column(col_values, r.params):
                add(ERROR, msg, row=row_idx, col=fdef.name)
```

`_is_empty` 判定:标量 None/"" 为空;数组 `[]` 为空。

### 6.3 错误分层(全部不抛异常)

| 层 | 何时 | 例子 | 存哪 / 报什么 |
|----|------|------|--------------|
| L1 标记层 | reader 识别 A 列 | `#rule[sep=,]` 与参数冲突 | `schema.parse_errors`(ERROR) |
| L2 规则层 | `parse_rule` | 未知规则名 `foo`;参数个数错 `range:1` | `FieldRule.parse_errors`(ERROR,checker 回显) |
| L3 类型层 | checker 执行前 | `regex` 用在 `int`;`range` 用在 `string` | checker 直接 add ERROR |

L2 让单条规则解析失败**不阻断其他规则**执行。

## 7. 报错格式

统一句式:`[规则名[:参数]] 字段 '<字段名>' <违规描述>: 行 <行号> 值 <实际值>`

**逐值规则**:
- `range:0,99999 字段 'hp' 超出范围: 行 5 值 -10`
- `regex:^\d{4}$ 字段 'id' 不匹配: 行 3 值 'abc'`
- `in:both,client,server 字段 'side' 不在集合内: 行 7 值 'all'`

**聚合规则**:
- `unique 字段 'id' 重复: 行 8 与行 3 值 1001`
- `sorted 字段 'id' 非严格递增: 行 8 值 1001 ≤ 行 7 值 1005`

**配置错误**(无行号,字段级):
- `规则 'range' 参数个数错误: 期望 2 个,实际 1 个`
- `规则 'regex' 不适用于类型 'int'`

所有违规走现有 `Issue` 结构。

## 8. 网页展示

规则违规自动出现在现有 issues 列表(零改动)。两个可选增强:

1. **扫描结果表加"规则"列**:读 `schema.to_dict().fields[].rules`,展示每字段约束。
2. **规则文档面板**:从 `REGISTRY` 自动生成(name/applicable_types/n_params 自描述),加规则时文档自动更新,不手维护。

## 9. 边界情况清单

| 情况 | 处理 |
|------|------|
| 字段无规则(`rules` 为空) | 跳过,只走内置检查 |
| `#rule` 行全行空单元格 | 不报错,等价无规则 |
| `#rule` 单元格切出空段(`;` 残留) | 空段跳过,不报错 |
| 字段是数组,规则是标量规则(`range`) | L3 类型错:`range 不适用于 int[]` |
| 数组字段用 `elem_range` | 正常,逐元素校验 |
| 数组字段用 `unique` | 聚合:整个数组作为一个值参与唯一性判断 |
| 数组字段用 `len` | 校验数组长度,正常 |
| 主键列重复配 `unique` | 不报错(去重);与主键内置唯一检查等效 |
| 规则参数含 `,`(`in:a,b,c`) | 正常,`,` 是参数分隔符 |
| 同字段重复写 `unique` | 去重保留一份,不报错 |

## 10. 测试策略

- **rules.py 单测**:每条规则的 `validate_params` / `check_value` / `check_column`,含正常 + 边界 + 错误用例。
- **excel_reader 单测**:`#rule` 行解析、多行累加、去重、稀疏、sep 配置、两层切分。
- **checker 单测**:规则调度、L2/L3 错误回显、空值跳过、聚合规则定位。
- **集成**:构造含 `#rule` 的样例表,端到端跑 scan → check → build,验证违规阻断导出。
- 在 `sample/` 增补带 `#rule` 的示例表,供手动验证与文档截图。
