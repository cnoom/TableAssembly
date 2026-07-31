"""checker 调度规则:L2 回显、L3 类型守卫、空值跳过、聚合定位、逐值定位。"""
from app import checker
from app.schema import FieldRule, T_INT, T_STRING

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
    # 用非主键字段隔离 unique 规则(避免内置「主键唯一」检查一起满足断言)
    # rows:[(row_index, [id, code]), ...];id 列唯一,code 列 1001 在行 4 重复
    f_id = make_field("id", T_INT)  # 主键,值唯一,不触发内置主键检查
    f_code = make_field("code", T_INT, rules=[FieldRule(name="unique", params=[], parse_errors=[])])
    s = make_schema(fields=[f_id, f_code], rows=[(2, [1, 1001]), (3, [2, 1002]), (4, [3, 1001])])
    rep = checker.check_table(s)
    errs = _errors(rep)
    # code 字段在行 4 因 unique 规则报错(1001 与行 2 重复)
    assert any(r == 4 and c == "code" for (r, c, _) in errs)
    assert any("unique" in m and "code" in m for (_, _, m) in errs)


# —— 无规则字段不受影响 ——
def test_no_rules_unchanged():
    f = make_field("hp", T_INT)
    s = make_schema(fields=[f], rows=[(2, [50])])
    rep = checker.check_table(s)
    assert rep.ok
