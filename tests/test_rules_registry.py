"""rules.py 骨架:parse_rule 切分、REGISTRY 查询、空段处理。"""
import pytest

from app import rules
from app.rules import parse_rule, REGISTRY


@pytest.mark.skip(reason="Task 3 注册 UniqueRule 后取消跳过:断言 parse_errors==[] 需规则已注册")
def test_parse_rule_no_params():
    fr = parse_rule("unique")
    assert fr.name == "unique"
    assert fr.params == []
    assert fr.parse_errors == []


@pytest.mark.skip(reason="Task 4 注册 RangeRule 后取消跳过:断言 parse_errors==[] 需规则已注册")
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


@pytest.mark.skip(reason="Task 3 注册 UniqueRule 后取消跳过")
def test_registry_lookup_returns_class():
    cls = REGISTRY.get("unique")
    assert cls is not None
    assert cls.name == "unique"


def test_registry_unknown_returns_none():
    assert REGISTRY.get("nope") is None
