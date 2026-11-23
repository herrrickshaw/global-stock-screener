"""Offline tests for delivery_signal: fetch/cache/report paths with the network faked."""

import datetime as dt
import sys
import types

import numpy as np
import pandas as pd
import pytest

import delivery_signal as ds


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "CACHE", tmp_path)
    return tmp_path


CSV = (
    "SYMBOL, SERIES, DELIV_PER, TTL_TRD_QNTY\n"
    "AAA, EQ, 55.5, 1000\n"
    "BBB, BE, 40, 500\n"
    "CCC, EQ, -, 300\n"
    "DDD, EQ, 70, 900\n"
)


class Resp:
    def __init__(self, status=200, content=b""):
        self.status_code = status
        self.content = content


def fake_requests(monkeypatch, fn):
    mod = types.ModuleType("requests")
    mod.get = fn
    monkeypatch.setitem(sys.modules, "requests", mod)


def test_fetch_day_parses_and_filters(monkeypatch):
    seen = {}

    def get(url, headers=None, timeout=None):
        seen.update(url=url, timeout=timeout)
        return Resp(200, CSV.encode())

    fake_requests(monkeypatch, get)
    out = ds._fetch_day(dt.date(2026, 3, 9))
    assert seen["url"].endswith("sec_bhavdata_full_09032026.csv")
    assert seen["timeout"] == 25
    # BE series dropped, unparsable DELIV_PER dropped
    assert list(out["Symbol"]) == ["AAA", "DDD"]
    assert list(out["DelivPct"]) == [55.5, 70.0]
    assert list(out["Volume"]) == [1000, 900]
    assert (out["Date"] == pd.Timestamp(2026, 3, 9)).all()


@pytest.mark.parametrize("resp", [Resp(404, b"x"), Resp(200, b""), Resp(500, b"")])
def test_fetch_day_http_failures_none(monkeypatch, resp):
    fake_requests(monkeypatch, lambda *a, **k: resp)
    assert ds._fetch_day(dt.date(2026, 3, 9)) is None


def test_fetch_day_exception_none(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("net")

    fake_requests(monkeypatch, boom)
    assert ds._fetch_day(dt.date(2026, 3, 9)) is None
    # malformed CSV (missing columns) is swallowed too
    fake_requests(monkeypatch, lambda *a, **k: Resp(200, b"A,B\n1,2\n"))
    assert ds._fetch_day(dt.date(2026, 3, 9)) is None


class FixedDate(dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 3, 11)  # Wednesday


def test_fetch_skips_weekends_and_known_days(cache, monkeypatch, capsys):
    monkeypatch.setattr(ds._dt, "date", FixedDate)
    calls = []

    def fake_day(d):
        calls.append(d)
        if d == dt.date(2026, 3, 10):
            return None  # failed day
        if d == dt.date(2026, 3, 6):
            return pd.DataFrame()  # empty day
        return pd.DataFrame(
            {"Date": [pd.Timestamp(d)], "Symbol": ["AAA"], "DelivPct": [50.0], "Volume": [1]}
        )

    monkeypatch.setattr(ds, "_fetch_day", fake_day)
    # pre-seed 2026-03-09 so it is skipped
    pd.DataFrame(
        {"Date": [pd.Timestamp(2026, 3, 9)], "Symbol": ["AAA"], "DelivPct": [10.0], "Volume": [1]}
    ).to_parquet(cache / "IN.parquet", index=False)
    got = ds.fetch(days=7)
    # days: 03-11 (Wed ok), 03-10 (fail), 03-09 (known), 03-08/07 weekend, 03-06 (empty), 03-05 (ok)
    assert [c for c in calls] == [
        dt.date(2026, 3, 11),
        dt.date(2026, 3, 10),
        dt.date(2026, 3, 6),
        dt.date(2026, 3, 5),
    ]
    assert got == 2
    saved = pd.read_parquet(cache / "IN.parquet")
    assert sorted(saved["Date"].dt.date) == [
        dt.date(2026, 3, 5),
        dt.date(2026, 3, 9),
        dt.date(2026, 3, 11),
    ]
    assert "+2 new day(s), IN.parquet now 3 rows" in capsys.readouterr().out


def test_fetch_nothing_new_does_not_write_and_quiet(cache, monkeypatch, capsys):
    monkeypatch.setattr(ds._dt, "date", FixedDate)
    monkeypatch.setattr(ds, "_fetch_day", lambda d: None)
    assert ds.fetch(days=3, verbose=False) == 0
    assert not (cache / "IN.parquet").exists()
    assert capsys.readouterr().out == ""
    assert ds.fetch(days=1) == 0
    assert "+0 new day(s), IN.parquet now 0 rows" in capsys.readouterr().out


def test_fetch_dedups_same_symbol_date(cache, monkeypatch):
    monkeypatch.setattr(ds._dt, "date", FixedDate)
    d0 = pd.DataFrame(
        {"Date": [pd.Timestamp(2026, 3, 11)] * 2, "Symbol": ["A", "A"], "DelivPct": [1.0, 2.0], "Volume": [1, 1]}
    )
    monkeypatch.setattr(ds, "_fetch_day", lambda d: d0)
    ds.fetch(days=1, verbose=False)
    saved = pd.read_parquet(cache / "IN.parquet")
    assert len(saved) == 1 and saved["DelivPct"].iloc[0] == 2.0  # keep="last"


def _hist(sym, vals):
    return pd.DataFrame(
        {
            "Date": pd.date_range("2026-01-01", periods=len(vals)),
            "Symbol": sym,
            "DelivPct": vals,
            "Volume": 1,
        }
    )


def test_accumulation_signal_boundaries():
    base = [50.0] * 20
    def sig(recent):
        df = _hist("X", base + recent)
        return ds.accumulation_scores(df).iloc[0]

    assert sig([57.5] * 5)["Signal"] == "ACCUMULATION"  # ratio exactly 1.15
    assert sig([57.4] * 5)["Signal"] == "NEUTRAL"
    assert sig([40.0] * 5)["Signal"] == "DISTRIBUTION"  # exactly 0.8
    assert sig([40.1] * 5)["Signal"] == "NEUTRAL"
    # rec >= 60 and ratio >= 1.1 -> strong
    strong = ds.accumulation_scores(_hist("X", [50.0] * 20 + [60.0] * 5)).iloc[0]
    assert strong["Signal"] == "STRONG ACCUMULATION" and strong["AccumScore"] == 1.2
    # rec just under 60 with ratio >=1.15 -> plain accumulation
    assert (
        ds.accumulation_scores(_hist("X", [50.0] * 20 + [59.9] * 5)).iloc[0]["Signal"]
        == "ACCUMULATION"
    )
    # rec >= 60 but ratio 1.05 -> neutral
    assert (
        ds.accumulation_scores(_hist("X", [57.0] * 20 + [60.0] * 5)).iloc[0]["Signal"] == "NEUTRAL"
    )


def test_accumulation_min_length_and_empty_and_zero_base():
    assert ds.accumulation_scores(pd.DataFrame()).empty
    assert list(ds.accumulation_scores(pd.DataFrame()).columns) == [
        "Symbol", "DelivRecent", "DelivBase", "AccumScore", "Signal"
    ]
    # needs recent + 3 observations
    assert ds.accumulation_scores(_hist("X", [50.0] * 7)).empty
    assert len(ds.accumulation_scores(_hist("X", [50.0] * 8))) == 1
    # zero baseline skipped
    assert ds.accumulation_scores(_hist("X", [0.0] * 10 + [50.0] * 5)).empty
    # nan baseline skipped
    assert ds.accumulation_scores(_hist("X", [np.nan] * 10 + [50.0] * 5)).empty


def test_accumulation_sorted_and_params():
    df = pd.concat([_hist("LOW", [50.0] * 25), _hist("HI", [50.0] * 20 + [70.0] * 5)])
    out = ds.accumulation_scores(df)
    assert list(out["Symbol"]) == ["HI", "LOW"]
    assert list(out.index) == [0, 1]
    # recent=2: base window is the 20 before; with 8 points base = d[:-2] when shorter
    out2 = ds.accumulation_scores(_hist("X", [10.0] * 6 + [20.0] * 2), recent=2, base=20)
    row = out2.iloc[0]
    assert row["DelivRecent"] == 20.0 and row["DelivBase"] == 10.0 and row["AccumScore"] == 2.0
    # base window caps at `base` observations
    out3 = ds.accumulation_scores(_hist("X", [100.0] * 10 + [10.0] * 3 + [20.0] * 2), recent=2, base=3)
    assert out3.iloc[0]["DelivBase"] == 10.0


def test_delivery_map_and_report(cache, capsys):
    assert ds.delivery_map() == {}
    assert ds.report().empty
    assert "no delivery cache" in capsys.readouterr().out
    assert ds.report(verbose=False).empty
    assert capsys.readouterr().out == ""

    df = pd.concat(
        [
            _hist("UP", [50.0] * 20 + [70.0] * 5),
            _hist("DN", [50.0] * 20 + [30.0] * 5),
            _hist("FLAT", [50.0] * 25),
        ]
    )
    df.to_parquet(cache / "IN.parquet", index=False)
    assert ds.delivery_map() == {"UP": 70.0, "FLAT": 50.0, "DN": 30.0}
    sc = ds.report(top=1)
    out = capsys.readouterr().out
    assert list(sc["Symbol"]) == ["UP", "FLAT", "DN"]
    assert "NSE delivery-% accumulation" in out
    assert "1 accumulating, 1 distributing" in out
    table = out.split("(top) ===\n")[1].split("\n\n")[0]
    assert "UP" in table and "FLAT" not in table and "DN" not in table  # head(top=1)
    assert not ds.report(verbose=False).empty
    assert capsys.readouterr().out == ""


def test_report_empty_scores_silent(cache, capsys):
    _hist("X", [50.0] * 3).to_parquet(cache / "IN.parquet", index=False)
    assert ds.report().empty
    assert capsys.readouterr().out == ""
    assert ds.delivery_map() == {}


def test_main_fetch_flag(monkeypatch, cache):
    calls = []
    monkeypatch.setattr(ds, "fetch", lambda days: calls.append(("fetch", days)))
    monkeypatch.setattr(ds, "report", lambda top: calls.append(("report", top)))
    monkeypatch.setattr(sys, "argv", ["ds", "--fetch", "--days", "5", "--top", "3"])
    assert ds.main() == 0
    assert calls == [("fetch", 5), ("report", 3)]
    calls.clear()
    monkeypatch.setattr(sys, "argv", ["ds"])
    assert ds.main() == 0
    assert calls == [("report", 20)]
