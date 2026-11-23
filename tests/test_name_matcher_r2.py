"""name_matcher: normalisation, index build (fake symbol master + company list), match tiers."""

import sys
import types

import pandas as pd
import pytest

import name_matcher as nm


@pytest.fixture(autouse=True)
def fresh_cache():
    nm._index.cache_clear()
    yield
    nm._index.cache_clear()


def master(monkeypatch, df=None, raises=False):
    mod = types.ModuleType("symbol_master")

    def load_master():
        if raises:
            raise RuntimeError("x")
        return df

    mod.load_master = load_master
    monkeypatch.setitem(sys.modules, "symbol_master", mod)


def test_clean_strips_noise_and_punctuation():
    assert nm.clean("Reliance Industries Ltd.") == "reliance"
    assert nm.clean("The Tata Consultancy Services Limited") == "tata consultancy"
    assert nm.clean("  AT&T  Inc ") == "at t"
    assert nm.clean("M&M") == "m m"
    assert nm.clean("") == "" and nm.clean(None) == "none"
    assert nm.clean("Infosys-Tech") == "infosys"
    assert nm.clean("Co") == ""  # only noise


def test_index_from_master_first_wins_and_skips_blank(monkeypatch, tmp_path):
    monkeypatch.setattr(nm, "HERE", tmp_path)
    master(
        monkeypatch,
        pd.DataFrame(
            {
                "name": ["Reliance Industries Ltd", "Reliance Ltd", "Ltd", "Infosys Limited"],
                "symbol": ["RELIANCE", "REL2", "BLANK", "INFY"],
            }
        ),
    )
    exact, second, names = nm._index("IN")
    assert exact == {"reliance": "RELIANCE", "infosys": "INFY"}  # first wins; 'ltd' cleans to ''
    assert second == {} and names == ("reliance", "infosys")


@pytest.mark.parametrize("df", [None, pd.DataFrame()])
def test_index_empty_or_missing_master(monkeypatch, tmp_path, df):
    monkeypatch.setattr(nm, "HERE", tmp_path)
    master(monkeypatch, df)
    assert nm._index("IN")[0] == {}


def test_index_master_failure_swallowed(monkeypatch, tmp_path):
    monkeypatch.setattr(nm, "HERE", tmp_path)
    master(monkeypatch, raises=True)
    assert nm._index("IN")[0] == {}


def test_index_company_list_market_scoped_with_ticker_alias(monkeypatch, tmp_path):
    monkeypatch.setattr(nm, "HERE", tmp_path)
    master(monkeypatch, None)
    (tmp_path / "cache_seed").mkdir()
    pd.DataFrame(
        {
            "Market": ["IN", "US", "IN"],
            "Name": ["Tata Motors Ltd", "Apple Inc", ""],
            "Symbol": ["TATAMOTORS", "AAPL", "XYZ"],
        }
    ).to_parquet(tmp_path / "cache_seed" / "company_list.parquet")
    exact, _, _ = nm._index("IN")
    assert exact == {"tata motors": "TATAMOTORS", "tatamotors": "TATAMOTORS", "xyz": "XYZ"}
    assert nm._index("US")[0] == {"apple": "AAPL", "aapl": "AAPL"}


def test_index_company_list_without_market_column(monkeypatch, tmp_path):
    monkeypatch.setattr(nm, "HERE", tmp_path)
    master(monkeypatch, None)
    (tmp_path / "cache_seed").mkdir()
    pd.DataFrame({"Name": ["Foo Corp"], "Symbol": ["FOO"]}).to_parquet(
        tmp_path / "cache_seed" / "company_list.parquet"
    )
    assert nm._index("ANY")[0] == {"foo": "FOO"}


@pytest.fixture
def idx(monkeypatch, tmp_path):
    monkeypatch.setattr(nm, "HERE", tmp_path)
    master(
        monkeypatch,
        pd.DataFrame(
            {
                "name": [
                    "Reliance Industries Ltd",
                    "Tata Consultancy Services",
                    "Infosys Ltd",
                    "HDFC Bank Ltd",
                    "State Bank of India",
                ],
                "symbol": ["RELIANCE", "TCS", "INFY", "HDFCBANK", "SBIN"],
            }
        ),
    )


def test_match_exact_substring_fuzzy_none(idx):
    assert nm.match("Reliance Industries Limited") == ("RELIANCE", 1.0)
    assert nm.match("") is None and nm.match("Ltd") is None
    # substring, length gap <= 6: 'hdfc bank' vs 'hdfc banking' (gap 3)
    assert nm.match("HDFC Banking") == ("HDFCBANK", 0.95)
    # substring but length gap > 6 is not accepted by tier 2 ('tata' vs 'tata consultancy')
    assert nm.match("Tata", cutoff=0.99) is None
    # gap exactly 6 accepted ('infosys abcde' is 13 chars vs 7); gap 7 rejected
    assert nm.match("Infosys abcde") == ("INFY", 0.95)
    assert nm.match("Infosys abcdef") is None
    # fuzzy: typo
    t, s = nm.match("Relience")
    assert t == "RELIANCE" and 0.82 <= s < 1.0 and s == round(s, 2)
    assert nm.match("zzzzqqqq") is None
    # cutoff parameter respected
    assert nm.match("Relience", cutoff=0.99) is None


def test_resolve_splits_hits_and_misses(idx):
    hits, misses = nm.resolve(["Infosys", "Nonexistent Co Zq", "State Bank of India"])
    assert hits == {"Infosys": ("INFY", 1.0), "State Bank of India": ("SBIN", 1.0)}
    assert misses == ["Nonexistent Co Zq"]
    assert nm.resolve([]) == ({}, [])
