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
