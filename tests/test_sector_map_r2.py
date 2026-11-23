"""Offline tests for sector_map: yfinance and serving view faked, cache redirected to tmp_path."""

import sys
import types

import numpy as np
import pandas as pd
import pytest

import sector_map as sm


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "CACHE", tmp_path)
    monkeypatch.setattr(sm.time, "sleep", lambda s: None)
    return tmp_path


def fake_yf(monkeypatch, infos):
    asked = []

    class Ticker:
        def __init__(self, t):
            asked.append(t)
            self.t = t

        @property
        def info(self):
            v = infos[self.t]
            if isinstance(v, Exception):
                raise v
            return v

    mod = types.ModuleType("yfinance")
    mod.Ticker = Ticker
    monkeypatch.setitem(sys.modules, "yfinance", mod)
    return asked


def serving_df():
    return pd.DataFrame({"Symbol": ["A", "B", "C", "D"], "Turnover_USD": [1.0, 4.0, 3.0, 2.0]})


def test_cache_path(cache):
    assert sm._cache_path("IN") == cache / "IN.parquet"


def test_fetch_ranks_by_turnover_limits_and_suffix(cache, monkeypatch, capsys):
    asked = fake_yf(
        monkeypatch,
        {
            "B.NS": {"sector": "Tech"},
            "C.NS": {"sector": None, "industryGroup": "Banks"},
            "D.NS": {},
            "A.NS": {"sector": "Energy"},
        },
    )
    monkeypatch.setattr(sm.sl, "serving", lambda m: serving_df())
    got = sm.fetch("IN", limit=3)
    # top by turnover: B, C, D (limit=3 -> head(6) is all four, want[:3])
    assert asked == ["B.NS", "C.NS", "D.NS"]
    assert got == 2  # D has no sector
    saved = pd.read_parquet(cache / "IN.parquet")
    assert dict(zip(saved.Symbol, saved.Sector)) == {"B": "Tech", "C": "Banks"}
    assert "sectors[IN]: +2 tagged, 2 total cached" in capsys.readouterr().out


def test_fetch_symbols_arg_skips_known_and_dedups(cache, monkeypatch, capsys):
    pd.DataFrame({"Symbol": ["A", "B"], "Sector": ["Old", "Keep"]}).to_parquet(
        cache / "US.parquet", index=False
    )
    asked = fake_yf(monkeypatch, {"C": {"sector": "New"}, "Z": RuntimeError("boom")})
    got = sm.fetch("US", symbols=["A", "C", "Z"], verbose=False)
    assert asked == ["C", "Z"]  # A already cached; US has no suffix; Z raises -> skipped
    assert got == 1
    d = dict(pd.read_parquet(cache / "US.parquet").values.tolist())
    assert d == {"A": "Old", "B": "Keep", "C": "New"}
    assert capsys.readouterr().out == ""


def test_fetch_progress_every_50(cache, monkeypatch, capsys):
    syms = [f"S{i}" for i in range(100)]
    fake_yf(monkeypatch, {s: {"sector": "X"} for s in syms})
    assert sm.fetch("US", symbols=syms) == 100
    out = capsys.readouterr().out
    assert "tagged 50/100" in out and "tagged 100/100" in out
    assert out.count("…") == 2


def test_fetch_no_serving_view(cache, monkeypatch, capsys):
    fake_yf(monkeypatch, {})
    monkeypatch.setattr(sm.sl, "serving", lambda m: pd.DataFrame())
    assert sm.fetch("IN") == 0
    assert "no serving view for IN" in capsys.readouterr().out
    assert sm.fetch("IN", verbose=False) == 0
    assert capsys.readouterr().out == ""


def test_fetch_without_turnover_column_keeps_order(cache, monkeypatch):
    asked = fake_yf(monkeypatch, {"A": {"sector": "x"}, "B": {"sector": "y"}})
    monkeypatch.setattr(sm.sl, "serving", lambda m: pd.DataFrame({"Symbol": ["A", "B"]}))
    sm.fetch("US", verbose=False)
    assert asked == ["A", "B"]


def test_fetch_nothing_tagged_writes_nothing(cache, monkeypatch):
    fake_yf(monkeypatch, {"A": {}})
    assert sm.fetch("US", symbols=["A"], verbose=False) == 0
    assert not (cache / "US.parquet").exists()


def test_sector_map_roundtrip(cache):
    assert sm.sector_map("IN") == {}
    pd.DataFrame({"Symbol": ["A"], "Sector": ["Tech"]}).to_parquet(cache / "IN.parquet")
    assert sm.sector_map("IN") == {"A": "Tech"}


def _srv(rows):
    return pd.DataFrame(rows, columns=["Symbol", "Ret252", "Ret63", "Above200DMA"])


def test_rotation_empty_inputs():
    cols = ["Sector", "Names", "MedRet252", "MedRet63", "Breadth", "Phase"]
    assert list(sm.rotation(pd.DataFrame(), {"A": "x"}).columns) == cols
    assert sm.rotation(_srv([("A", 1, 1, 1)]), {}).empty
    # all below min_names -> empty frame
    assert sm.rotation(_srv([("A", 1, 1, 1)]), {"A": "x"}).empty


def test_rotation_phase_boundaries():
    def one(r252, r63, above_frac):
        n = 10
        k = round(above_frac * n)
        rows = [(f"S{i}", r252, r63, 1 if i < k else 0) for i in range(n)]
        smap = {f"S{i}": "Sec" for i in range(n)}
        return sm.rotation(_srv(rows), smap).iloc[0]["Phase"]

    assert one(26, 1, 0.6) == "Peak Boom"
    assert one(25, 1, 0.6) == "Early Boom"  # >25 strict
    assert one(10, 0.1, 0.6) == "Early Boom"
    assert one(10, 0, 0.6) == "Cooling"  # r63 must be >0; breadth .6 not <=.35
    assert one(10, 1, 0.5) == "Cooling"
    assert one(10, 1, 0.3) == "Laggard"  # breadth <= .35
    assert one(10, 1, 0.4) == "Cooling"
    assert one(10, -5, 0.5) == "Cooling"  # r63 < -5 strict
    assert one(10, -5.1, 0.5) == "Laggard"


def test_rotation_min_names_boundary_values_and_sort():
    rows = (
        [("A1", 10, 2, 1), ("A2", 20, 4, 1), ("A3", 30, 6, 0)]
        + [("B1", 5, 1, 1), ("B2", 5, 1, 1), ("B3", 5, 1, 1)]
        + [("C1", 5, 1, 1), ("C2", 5, 1, 1)]  # only 2 names
        + [("U1", 5, 1, 1)]  # unmapped symbol dropped
    )
    smap = {r[0]: r[0][0] for r in rows[:-1]}
    out = sm.rotation(_srv(rows), smap)
    assert list(out["Sector"]) == ["B", "A"]  # breadth 1.0 then 0.67
    a = out[out.Sector == "A"].iloc[0]
    assert a.Names == 3 and a.MedRet252 == 20.0 and a.MedRet63 == 4.0 and a.Breadth == 0.67
    # min_names param lowers the bar
    out2 = sm.rotation(_srv(rows), smap, min_names=2)
    assert set(out2["Sector"]) == {"A", "B", "C"}
    # tie on breadth -> higher MedRet63 first
    rows3 = [
        ("X1", 1, 9, 1),
        ("X2", 1, 9, 1),
        ("X3", 1, 9, 1),
        ("Y1", 1, 1, 1),
        ("Y2", 1, 1, 1),
        ("Y3", 1, 1, 1),
    ]
    smap3 = {r[0]: r[0][0] for r in rows3}
    assert list(sm.rotation(_srv(rows3), smap3)["Sector"]) == ["X", "Y"]


def test_rotation_missing_columns_nan():
    df = pd.DataFrame({"Symbol": ["A", "B", "C"]})
    out = sm.rotation(df, {"A": "s", "B": "s", "C": "s"})
    r = out.iloc[0]
    assert np.isnan(r.MedRet252) and np.isnan(r.MedRet63) and np.isnan(r.Breadth)
    assert r.Phase == "Cooling"


def test_report_paths(cache, monkeypatch, capsys):
    assert sm.report("IN").empty
    assert "no sector cache" in capsys.readouterr().out
    assert sm.report("IN", verbose=False).empty
    assert capsys.readouterr().out == ""
    pd.DataFrame({"Symbol": ["A", "B", "C"], "Sector": ["Hot"] * 3}).to_parquet(
        cache / "IN.parquet"
    )
    monkeypatch.setattr(
        sm.sl, "serving", lambda m: _srv([("A", 30, 3, 1), ("B", 30, 3, 1), ("C", 30, 3, 1)])
    )
    out = sm.report("IN")
    txt = capsys.readouterr().out
    assert out.iloc[0]["Phase"] == "Peak Boom"
    assert "Sector rotation — IN (3 tagged)" in txt
    assert "booming sectors (hunt here): ['Hot']" in txt
    # laggard only -> no booming line
    monkeypatch.setattr(
        sm.sl, "serving", lambda m: _srv([("A", 1, -9, 0), ("B", 1, -9, 0), ("C", 1, -9, 0)])
    )
    sm.report("IN")
    assert "booming" not in capsys.readouterr().out
    # empty rotation -> quiet
    monkeypatch.setattr(sm.sl, "serving", lambda m: pd.DataFrame())
    assert sm.report("IN").empty
    assert capsys.readouterr().out == ""


def test_main(monkeypatch):
    calls = []
    monkeypatch.setattr(sm, "fetch", lambda m, n: calls.append(("f", m, n)))
    monkeypatch.setattr(sm, "report", lambda m: calls.append(("r", m)))
    monkeypatch.setattr(sys, "argv", ["sm", "--fetch", "--market", "US", "--limit", "7"])
    assert sm.main() == 0
    assert calls == [("f", "US", 7), ("r", "US")]
    calls.clear()
    monkeypatch.setattr(sys, "argv", ["sm"])
    sm.main()
    assert calls == [("r", "IN")]


def test_rotation_breadth_exactly_035_is_laggard():
    n = 20
    rows = [(f"S{i}", 10, 1, 1 if i < 7 else 0) for i in range(n)]  # breadth 7/20 = 0.35
    out = sm.rotation(_srv(rows), {f"S{i}": "Sec" for i in range(n)})
    assert out.iloc[0]["Breadth"] == 0.35 and out.iloc[0]["Phase"] == "Laggard"


def test_fetch_skips_cached_before_applying_limit(cache, monkeypatch):
    pd.DataFrame({"Symbol": ["B", "C"], "Sector": ["x", "y"]}).to_parquet(
        cache / "IN.parquet", index=False
    )
    asked = fake_yf(monkeypatch, {"A.NS": {"sector": "s"}, "D.NS": {"sector": "t"}})
    monkeypatch.setattr(sm.sl, "serving", lambda m: serving_df())  # turnover: B, C, D, A
    sm.fetch("IN", limit=2, verbose=False)
    # the top-`limit` names (B, C) are already cached, so the next uncached ones are tagged
    assert asked == ["D.NS", "A.NS"]
