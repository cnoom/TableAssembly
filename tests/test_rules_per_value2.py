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
