# Tests for the OHLC fill-rate threshold challenge.
import repo_dashboard as rd


def test_low_fill_flags_red():
    metrics = {"gov_fail": [], "todo": 0}
    status = {"source_fill": {"requested": 1000, "filled": 800}}  # 80% < 90%
    out = rd._challenges(["IN"], metrics, status)
    assert "OHLC fill low" in out and "80%" in out and "EODHD" in out


def test_healthy_fill_no_flag():
    metrics = {"gov_fail": [], "todo": 0}
    status = {"source_fill": {"requested": 1000, "filled": 960}}  # 96% >= 90%
    out = rd._challenges(["IN"], metrics, status)
    assert "OHLC fill low" not in out


def test_missing_fill_no_crash():
    out = rd._challenges(["IN"], {"gov_fail": [], "todo": 0}, {})
    assert "OHLC fill low" not in out
