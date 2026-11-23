"""flows_regime + results_calendar with nsepython faked; storage redirected to tmp_path."""

import datetime as dt
import json
import sys
import types

import pandas as pd
import pytest

import flows_regime as fr
import results_calendar as rc


def fake_nse(monkeypatch, **attrs):
    mod = types.ModuleType("nsepython")
    for k, v in attrs.items():
        setattr(mod, k, v)
    monkeypatch.setitem(sys.modules, "nsepython", mod)
    return mod


@pytest.fixture
def store(tmp_path, monkeypatch):
    p = tmp_path / "IN.json"
    monkeypatch.setattr(fr, "STORE", p)
    return p


# ---------------- flows_regime.regime ----------------
def test_regime_empty_is_neutral_zero():
    r = fr.regime({})
    assert r == {"regime": "Neutral", "score": 0.0, "drivers": [], "asof": ""}


def test_regime_vix_component_and_clamps():
    assert fr.regime({"vix": 17})["score"] == 0.0
    assert fr.regime({"vix": 14})["score"] == 12.0  # (17-14)*4
    assert fr.regime({"vix": 20})["score"] == -12.0
    assert fr.regime({"vix": 1})["score"] == 40.0  # clamp +40
    assert fr.regime({"vix": 99})["score"] == -40.0  # clamp -40
    assert fr.regime({"vix": 14})["drivers"] == ["VIX 14.0"]


def test_regime_fii_dii_components_and_clamps():
    assert fr.regime({"fii_net": 1000})["score"] == 20.0
    assert fr.regime({"fii_net": 99999})["score"] == 40.0
    assert fr.regime({"fii_net": -99999})["score"] == -40.0
    assert fr.regime({"dii_net": 1000})["score"] == 10.0
    assert fr.regime({"dii_net": 99999})["score"] == 20.0
    assert fr.regime({"dii_net": -99999})["score"] == -20.0
    r = fr.regime({"fii_net": 0.0, "dii_net": 0.0})  # zero is present, not missing
    assert r["drivers"] == ["FII net ₹0cr", "DII net ₹0cr"]
    assert fr.regime({"fii_net": 1234.4, "dii_net": -5678.6})["drivers"] == [
        "FII net ₹1,234cr",
        "DII net ₹-5,679cr",
    ]


def test_regime_thresholds_strict():
    # vix 10.75 -> +25 exactly => Neutral (strict >25); a bit lower vix -> Risk-On
    assert fr.regime({"vix": 10.75})["regime"] == "Neutral"
    assert fr.regime({"vix": 10.7})["regime"] == "Risk-On"
    assert fr.regime({"vix": 23.25})["regime"] == "Neutral"  # -25
    assert fr.regime({"vix": 23.3})["regime"] == "Risk-Off"
    # composition, order of drivers, asof, rounding
    r = fr.regime({"vix": 15, "fii_net": 500, "dii_net": 250, "asof": "2026-01-02"})
    assert r["score"] == 8 + 10 + 2.5 and r["regime"] == "Neutral"
    assert r["drivers"][0].startswith("VIX") and r["drivers"][1].startswith("FII")
    assert r["asof"] == "2026-01-02"


def test_regime_loads_from_store_when_no_data(store):
    store.write_text(json.dumps({"vix": 10, "fii_net": 2000}))
    r = fr.regime()
    assert r["regime"] == "Risk-On" and r["score"] == 68.0
    assert fr.regime({})["score"] == 0.0  # explicit empty dict is not replaced by the store


def test_load_and_bias(store):
    assert fr._load() == {}
    assert fr.regime_bias() == 0.0
    store.write_text(json.dumps({"vix": 10}))
    assert fr._load() == {"vix": 10}
    assert fr.regime_bias() == 0.28
    store.write_text(json.dumps({"vix": 99, "fii_net": -99999, "dii_net": -99999}))
    assert fr.regime_bias() == -1.0


# ---------------- fetch ----------------
def test_fetch_collects_and_persists(store, monkeypatch, capsys):
    fake_nse(
        monkeypatch,
        nse_get_index_quote=lambda n: {"lastPrice": "13.5"},
        nse_fiidii=lambda: [
            {"category": "FII/FPI *", "netValue": "-1,0"},  # float() fails -> fiidii block aborted
        ],
    )
    out = fr.fetch()
    # vix survives the aborted fiidii block
    assert out["vix"] == 13.5 and "fii_net" not in out
    assert out["asof"] == dt.date.today().isoformat()
    assert json.loads(store.read_text()) == out
    assert "flows:" in capsys.readouterr().out


def test_fetch_fii_dii_rows(store, monkeypatch):
    fake_nse(
        monkeypatch,
        nse_get_index_quote=lambda n: (_ for _ in ()).throw(KeyError("x")),
        nse_fiidii=lambda: [
            {"category": "DII", "netValue": "250.5"},
            {"category": "fpi", "net": "-100"},
            {"category": "other", "netValue": "9"},
            {"category": "FII", "netValue": None},
        ],
    )
    out = fr.fetch(verbose=False)
    assert "vix" not in out
    assert out["dii_net"] == 250.5
    assert out["fii_net"] == 0.0  # None -> 0 via `or 0`, last FII row wins


def test_fetch_non_list_fiidii_and_total_failure(store, monkeypatch, capsys):
    fake_nse(monkeypatch, nse_get_index_quote=lambda n: {"lastPrice": 20}, nse_fiidii=lambda: {"a": 1})
    out = fr.fetch(verbose=False)
    assert set(out) == {"vix", "asof"} and out["vix"] == 20.0
    # nothing at all -> nothing written, failure message
    store.unlink()
    fake_nse(monkeypatch, nse_get_index_quote=lambda n: 1 / 0, nse_fiidii=lambda: 1 / 0)
    assert fr.fetch() == {}
    assert not store.exists()
    assert "fetch failed (nsepython/network)" in capsys.readouterr().out


def test_fetch_without_nsepython(store, monkeypatch):
    monkeypatch.setitem(sys.modules, "nsepython", None)  # import raises ImportError
    assert fr.fetch(verbose=False) == {}
    assert not store.exists()


def test_flows_main(store, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["fr"])
    assert fr.main() == 0
    assert "India regime: Neutral  (score 0.0) — no data — run --fetch" in capsys.readouterr().out
    called = []
    monkeypatch.setattr(fr, "fetch", lambda: called.append(1) or {})
    store.write_text(json.dumps({"vix": 14, "fii_net": 100}))
    monkeypatch.setattr(sys, "argv", ["fr", "--fetch"])
    fr.main()
    assert called == [1]
    assert "India regime: Neutral  (score 14.0) — VIX 14.0, FII net ₹100cr" in capsys.readouterr().out


# ---------------- results_calendar ----------------
T = dt.date(2026, 3, 10)


def test_date_parsing_formats():
    assert rc._d("2026-03-10") == T
    assert rc._d("10-Mar-2026") == T
    assert rc._d("10 Mar 2026") == T
    assert rc._d("10/03/2026") is None and rc._d("") is None and rc._d("garbage") is None


def test_days_to_event_and_near_event_boundaries():
    assert rc.days_to_event("2026-03-15", T) == 5
    assert rc.days_to_event("2026-03-05", T) == -5
    assert rc.days_to_event("bad", T) is None
    assert rc.days_to_event("2026-03-10", T) == 0
    assert rc.near_event("2026-03-15", 5, T) is True
    assert rc.near_event("2026-03-16", 5, T) is False
    assert rc.near_event("2026-03-05", 5, T) is True
    assert rc.near_event("2026-03-04", 5, T) is False
    assert rc.near_event("bad", 5, T) is False
    assert rc.near_event("2026-03-12", 1, T) is False and rc.near_event("2026-03-11", 1, T) is True


def test_days_to_event_defaults_to_today():
    today = dt.date.today()
    assert rc.days_to_event(today.isoformat()) == 0
    assert rc.days_to_event((today + dt.timedelta(days=3)).isoformat()) == 3


def test_upcoming_window_is_forward_inclusive():
    ev = {
        "PAST": "2026-03-09",
        "TODAY": "2026-03-10",
        "EDGE": "2026-03-17",
        "OVER": "2026-03-18",
        "BAD": "x",
    }
    assert rc.upcoming(ev, 7, T) == ["TODAY", "EDGE"]
    assert rc.upcoming(ev, 0, T) == ["TODAY"]
    assert rc.upcoming({}, 7, T) == []


def test_fetch_events_dataframe_and_list(monkeypatch, capsys):
    df = pd.DataFrame(
        {
            "symbol": [" abc ", "DEF", "", "JKL"],
            "date": ["2026-03-12 00:00", "", "2026-03-13", "2026-03-14"],
            "purpose_date": ["", "2026-03-11", "", ""],
        }
    )
    fake_nse(monkeypatch, nse_events=lambda: df)
    out = rc.fetch_events()
    assert out == {"ABC": "2026-03-12", "DEF": "2026-03-11", "JKL": "2026-03-14"}
    assert "events fetched: 3" in capsys.readouterr().out
    fake_nse(monkeypatch, nse_events=lambda: [{"symbol": "x", "date": "2026-01-01"}, {"symbol": "y"}])
    assert rc.fetch_events(verbose=False) == {"X": "2026-01-01"}
    fake_nse(monkeypatch, nse_events=lambda: None)
    assert rc.fetch_events(verbose=False) == {}


def test_fetch_events_no_attr_and_failures(monkeypatch):
    fake_nse(monkeypatch)  # no nse_events attribute
    assert rc.fetch_events(verbose=False) == {}
    fake_nse(monkeypatch, nse_events=lambda: 1 / 0)
    assert rc.fetch_events(verbose=False) == {}
    monkeypatch.setitem(sys.modules, "nsepython", None)
    assert rc.fetch_events(verbose=False) == {}


def test_calendar_main(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["rc"])
    assert rc.main() == 0
    assert "(run --fetch; source may be throttled)" in capsys.readouterr().out
    soon = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    far = (dt.date.today() + dt.timedelta(days=20)).isoformat()
    monkeypatch.setattr(rc, "fetch_events", lambda: {"SOON": soon, "FAR": far})
    monkeypatch.setattr(sys, "argv", ["rc", "--fetch"])
    rc.main()
    assert capsys.readouterr().out.strip() == "reporting soon: ['SOON']"
    monkeypatch.setattr(sys, "argv", ["rc", "--fetch", "--within", "30"])
    rc.main()
    assert capsys.readouterr().out.strip() == "reporting soon: ['SOON', 'FAR']"


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="results_calendar.fetch_events slices dates to [:10], truncating dd-Mon-yyyy "
    "('11-Mar-2026' -> '11-Mar-202'), so the format _d() supports never parses",
)
def test_fetch_events_keeps_dd_mon_yyyy_parseable(monkeypatch):
    df = pd.DataFrame({"symbol": ["DEF"], "date": [""], "purpose_date": ["11-Mar-2026"]})
    fake_nse(monkeypatch, nse_events=lambda: df)
    ev = rc.fetch_events(verbose=False)
    assert rc.days_to_event(ev["DEF"], dt.date(2026, 3, 10)) == 1
