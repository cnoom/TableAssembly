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
