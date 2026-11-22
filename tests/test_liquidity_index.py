"""Tests for liquidity.py: FX lookup, building the turnover index, the cached lookup helpers and
the tier boundaries.

Offline: yfinance and screener_kit are fake modules, INDEX_PATH points into tmp_path and the
module-level turnover cache is reset for every test.
"""

import sys
import types

import numpy as np
import pandas as pd
import pytest

import liquidity as liq


@pytest.fixture(autouse=True)
def isolated_index(monkeypatch, tmp_path):
    monkeypatch.setattr(liq, "INDEX_PATH", tmp_path / "liquidity_index.parquet")
    monkeypatch.setattr(liq, "_CACHE_MAP", {})
    return tmp_path / "liquidity_index.parquet"


def _write_index(path, rows):
    pd.DataFrame(rows).to_parquet(path, index=False)


def _module(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


# ---- tier -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,market,expected",
    [
        (None, "US", "Unknown"),
        (float("nan"), "US", "Unknown"),  # a symbol missing from the index arrives as NaN
        (20_000_000, "US", "High"),  # US: High from 20M ...
        (19_999_999, "US", "Medium"),
        (2_000_000, "US", "Medium"),  # ... Medium from 2M
        (1_999_999, "US", "Low"),
        (5_000_000, "IN", "High"),  # thinner market, lower bars
        (500_000, "IN", "Medium"),
        (499_999, "IN", "Low"),
        (10_000_000, None, "High"),  # no market -> global 10M / 1M
        (1_000_000, "ZZ", "Medium"),  # unknown market -> global defaults
        (999_999, None, "Low"),
        (0, "US", "Low"),
    ],
)
def test_tier_boundaries(value, market, expected):
    assert liq.tier(value, market) == expected


def test_every_market_has_a_currency_and_sane_tier_bars():
    for m, (hi, med) in liq.MARKET_TIERS.items():
        assert m in liq.CCY and hi > med > 0
    assert liq.UNIT == {"UK": 100.0, "ZA": 100.0}  # pence / cents quoting


# ---- _fx_rates --------------------------------------------------------------------------


def _fx_frame(**series):
    cols = pd.MultiIndex.from_product([["Close"], list(series)])
    return pd.DataFrame(
        dict(zip(cols, series.values())), index=pd.date_range("2024-01-01", periods=3)
    )


def test_fx_rates_uses_latest_non_nan_close_and_skips_usd(monkeypatch):
    seen = {}

    def download(tickers, **kwargs):
        seen["tickers"], seen["kwargs"] = tickers, kwargs
        return _fx_frame(**{"INR=X": [82.0, 83.0, np.nan], "EUR=X": [0.9, 0.91, 0.92]})

    monkeypatch.setitem(sys.modules, "yfinance", _module("yfinance", download=download))
    fx = liq._fx_rates(["USD", "INR", "EUR", "INR"])
    assert fx == {"USD": 1.0, "INR": 83.0, "EUR": 0.92}  # INR: last *non-NaN* value
    assert seen["tickers"] == ["EUR=X", "INR=X"]  # sorted, de-duplicated, no USD
    assert seen["kwargs"]["period"] == "5d"


def test_fx_rates_marks_a_currency_missing_from_the_download_as_none(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "yfinance",
        _module("yfinance", download=lambda t, **k: _fx_frame(**{"INR=X": [83.0, 83.0, 83.0]})),
    )
    fx = liq._fx_rates(["INR", "JPY"])
    assert fx["INR"] == 83.0 and fx["JPY"] is None and fx["USD"] == 1.0


def test_fx_rates_download_failure_gives_none_for_every_currency(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("offline")

    monkeypatch.setitem(sys.modules, "yfinance", _module("yfinance", download=boom))
    assert liq._fx_rates(["INR", "EUR", "USD"]) == {"USD": 1.0, "INR": None, "EUR": None}


# ---- build_index ------------------------------------------------------------------------


def _ohlcv(close, volume, n=25):
    idx = pd.date_range("2024-01-01", periods=n)
    return pd.DataFrame(
        {"Close": np.full(n, float(close)), "Volume": np.full(n, float(volume))}, index=idx
    )


@pytest.fixture
def kit(monkeypatch):
    def install(markets, data):
        monkeypatch.setitem(
            sys.modules,
            "screener_kit",
            _module("screener_kit", MARKETS=markets, load=lambda m: data[m]),
        )

    return install


def test_build_index_converts_turnover_to_usd_and_applies_units(kit, monkeypatch, isolated_index):
    monkeypatch.setattr(liq, "_fx_rates", lambda ccys: {"USD": 1.0, "INR": 80.0, "GBP": 0.8})
    kit(
        ["US", "IN", "UK"],
        {
            "US": {"AAA": _ohlcv(10, 1_000_000)},  # 10 * 1e6 = 1e7 USD
            "IN": {"BBB": _ohlcv(100, 8_000_000)},  # 8e8 INR / 80 = 1e7 USD
            "UK": {"CCC": _ohlcv(500, 1_000_000)},  # 5e8 pence -> 5e6 GBP -> / 0.8 = 6.25e6 USD
        },
    )
    idx = liq.build_index(verbose=False).set_index("Symbol")
    assert idx.loc["AAA", "turnover_usd"] == pytest.approx(1e7)
    assert idx.loc["BBB", "turnover_usd"] == pytest.approx(1e7)
    assert idx.loc["CCC", "turnover_usd"] == pytest.approx(6.25e6)
    assert idx.loc["CCC", "Market"] == "UK" and idx.loc["CCC", "ltp"] == 500.0
    assert isolated_index.exists()
    assert pd.read_parquet(isolated_index)["Symbol"].tolist() == ["AAA", "BBB", "CCC"]


def test_build_index_uses_the_20_day_median_not_the_mean(kit, monkeypatch):
    monkeypatch.setattr(liq, "_fx_rates", lambda ccys: {"USD": 1.0})
    df = _ohlcv(10, 1_000_000, n=30)
    df.iloc[-1, df.columns.get_loc("Volume")] = 1e12  # one wild print in the window
    kit(["US"], {"US": {"AAA": df}})
    idx = liq.build_index(verbose=False)
    assert idx.loc[0, "turnover_usd"] == pytest.approx(1e7)  # median ignores the spike


def test_build_index_skips_unusable_rows_and_markets(kit, monkeypatch, isolated_index):
    monkeypatch.setattr(liq, "_fx_rates", lambda ccys: {"USD": 1.0, "JPY": None})
    kit(
        ["US", "JP"],
        {
            "US": {
                "GOOD": _ohlcv(10, 1_000_000),
                "SHORT": _ohlcv(10, 1_000_000, n=19),  # fewer than 20 sessions
                "NOVOL": _ohlcv(10, 1_000_000).drop(columns="Volume"),
                "ZERO": _ohlcv(10, 0),  # no turnover
                "NONE": None,
            },
            "JP": {"JPN": _ohlcv(1000, 1_000_000)},  # no FX rate -> whole market skipped
        },
    )
    idx = liq.build_index(verbose=False)
    assert idx["Symbol"].tolist() == ["GOOD"]


def test_build_index_with_no_data_returns_empty_and_writes_nothing(
    kit, monkeypatch, isolated_index
):
    monkeypatch.setattr(liq, "_fx_rates", lambda ccys: {"USD": 1.0})
    kit(["US"], {"US": {}})
    assert liq.build_index(verbose=False).empty
    assert not isolated_index.exists()


def test_build_index_reports_progress(kit, monkeypatch, capsys):
    monkeypatch.setattr(liq, "_fx_rates", lambda ccys: {"USD": 1.0})
    kit(["US"], {"US": {"AAA": _ohlcv(10, 1_000_000)}})
    liq.build_index()
    out = capsys.readouterr().out
    assert "US: indexed 1 stocks" in out and "liquidity index: 1 symbols" in out


# ---- cached lookups ---------------------------------------------------------------------

ROWS = [
    {"Symbol": "AAA", "Market": "US", "turnover_usd": 50e6, "ltp": 10.0},
    {"Symbol": "BBB", "Market": "US", "turnover_usd": 3e6, "ltp": 5.0},
    {"Symbol": "CCC", "Market": "IN", "turnover_usd": 7e6, "ltp": 100.0},
    {"Symbol": "DDD", "Market": "IN", "turnover_usd": 2e5, "ltp": 20.0},
]


def test_load_index_is_empty_when_no_file_exists():
    assert liq._load_index().empty
    assert liq.turnover("AAA") is None
    assert liq.liquid_symbols() == []


def test_turnover_returns_float_or_none(isolated_index):
    _write_index(isolated_index, ROWS)
    assert liq.turnover("BBB") == 3e6 and isinstance(liq.turnover("BBB"), float)
    assert liq.turnover("NOPE") is None


def test_liquid_symbols_filters_sorts_and_limits(isolated_index):
    _write_index(isolated_index, ROWS)
    assert liq.liquid_symbols() == ["AAA", "CCC", "BBB"]  # >= $1M, most liquid first
    assert liq.liquid_symbols(market="IN") == ["CCC"]  # DDD is below the $1M default
    assert liq.liquid_symbols(market="IN", min_usd=1e5) == ["CCC", "DDD"]
    assert liq.liquid_symbols(top=2) == ["AAA", "CCC"]
    assert liq.liquid_symbols(min_usd=100e6) == []


def test_turnover_map_is_cached_after_first_load(isolated_index):
    _write_index(isolated_index, ROWS)
    first = liq._turnover_map()
    assert first["AAA"] == 50e6
    _write_index(
        isolated_index, [{"Symbol": "NEW", "Market": "US", "turnover_usd": 1.0, "ltp": 1.0}]
    )
    assert liq._turnover_map() is first  # served from memory, the file is not re-read
    assert "NEW" not in liq._turnover_map()


def test_turnover_map_is_not_cached_while_the_index_is_missing(isolated_index):
    assert liq._turnover_map() == {}
    _write_index(isolated_index, ROWS)
    assert liq._turnover_map()["CCC"] == 7e6  # picked up once the index appears


# ---- annotate ---------------------------------------------------------------------------


def test_annotate_adds_turnover_and_market_aware_tiers(isolated_index):
    _write_index(isolated_index, ROWS)
    df = pd.DataFrame(
        {"Symbol": ["AAA", "BBB", "CCC", "DDD", "ZZZ"], "Market": ["US", "US", "IN", "IN", "US"]}
    )
    out = liq.annotate(df)
    assert out["Turnover_USD"].tolist()[:4] == [50e6, 3e6, 7e6, 2e5]
    assert np.isnan(out["Turnover_USD"].iloc[4])
    # US bars are 20M / 2M; IN bars are 5M / 0.5M -> the same $3-7M is judged per market
    assert out["Liquidity"].tolist() == ["High", "Medium", "High", "Low", "Unknown"]


def test_annotate_without_market_column_uses_global_tiers(isolated_index):
    _write_index(isolated_index, ROWS)
    out = liq.annotate(pd.DataFrame({"Ticker": ["AAA", "BBB", "DDD", "ZZZ"]}), symbol_col="Ticker")
    assert out["Liquidity"].tolist() == [
        "High",
        "Medium",
        "Low",
        "Unknown",
    ]  # 50M / 3M / 0.2M / n.a.


def test_annotate_does_not_mutate_its_input_and_passes_through_unusable_frames(isolated_index):
    _write_index(isolated_index, ROWS)
    df = pd.DataFrame({"Symbol": ["AAA"]})
    out = liq.annotate(df)
    assert list(df.columns) == ["Symbol"] and "Liquidity" in out.columns
    assert liq.annotate(None) is None
    empty = pd.DataFrame()
    assert liq.annotate(empty) is empty
    no_col = pd.DataFrame({"Other": [1]})
    assert liq.annotate(no_col) is no_col
