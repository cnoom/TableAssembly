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
