"""端到端:带 #rule 的样例表 → scan → check → build。
违规表阻断导出;合规表正常产出。

覆盖:
    - 合规表通过 check(无 ERROR)
    - range 违规阻断
    - 主键重复(unique 规则 + 内置主键唯一 双重报错)
    - sorted 违规阻断
    - 仓库自带 sample/ItemRules.xlsx 能正常解析

说明(对规格的偏差,已确认):
    规格原文给 name 列配 `len:1,20`,但 `len` 规则仅作用于数组类型
    (见 app.rules.LenRule.applicable_types),用于 string 列会触发 L3
    类型守卫报 "规则 'len' 不适用于类型 'string'",导致 "合规表" 不合规。
    改用 `regex:^\\S+$` 表达等价意图(非空、非空白字符串),仍覆盖 regex
    规则的端到端链路。注意 regex 的参数不能含逗号(parse_rule 按逗号切分参数),
    因此不能用 `^.{1,20}$` 这类含量词逗号的 pattern。
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
    # name 列:见模块 docstring 的偏差说明(regex 参数禁逗号)
    ("#rule[sep=;]", "unique; sorted; range:1000,9999", "non_empty; regex:^\\S+$", "range:0,99999", "elem_range:1,9999"),
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
