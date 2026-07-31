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
