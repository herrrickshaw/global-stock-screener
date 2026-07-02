# Tests for run-timing + source fill-rate rendering and capture.
import pipeline_runner as pr
import repo_dashboard as rd


def test_timing_card_renders():
    status = {
        "timing": {"data_update": 420.5, "scans": 90.0, "news": 16.0, "scan_total": 540.0},
        "source_fill": {
            "requested": 9278,
            "filled": 9100,
            "by_source": {"stooq": 6000, "yahoo": 3100},
        },
    }
    html = rd._run_timing(status)
    assert "Data update" in html and "420.5s" in html
    assert "9100/9278" in html
    assert "stooq: 6000" in html and "yahoo: 3100" in html


def test_timing_card_empty():
    assert "has not run" in rd._run_timing({})


def test_timed_records_seconds():
    status = {}
    out = pr._timed(status, "thing", lambda: 42)
    assert out == 42
    assert "thing" in status["timing"] and isinstance(status["timing"]["thing"], float)


def test_source_fill_degrades_without_data_sources(monkeypatch):
    import builtins

    real = builtins.__import__

    def blocked(name, *a, **k):
        if name == "data_sources":
            raise ImportError("no data_sources on this tree")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", blocked)
    assert pr._source_fill() == {}
