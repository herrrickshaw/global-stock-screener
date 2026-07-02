# Tests for api_health probing + dashboard card + challenge folding (no real network).
import api_health
import repo_dashboard as rd


def test_endpoints_registry_shape():
    assert len(api_health.ENDPOINTS) >= 8
    for name, meta in api_health.ENDPOINTS.items():
        assert meta["url"].startswith("https://") and meta["purpose"]


def test_probe_offline_degrades(monkeypatch):
    # force every probe to fail fast (no network dependency in CI)
    def boom(name, purpose, url, timeout):
        return {
            "name": name,
            "purpose": purpose,
            "ok": False,
            "code": "",
            "ms": 0,
            "error": "blocked",
        }

    monkeypatch.setattr(api_health, "_probe_one", boom)
    res = api_health.probe(timeout=1)
    assert len(res) == len(api_health.ENDPOINTS)
    s = api_health.summary(res)
    assert s["ok"] == 0 and s["total"] == len(res) and len(s["down"]) == s["total"]


def test_card_renders_from_status():
    status = {
        "api_health": [
            {"name": "Yahoo/yfinance", "purpose": "OHLC", "ok": True, "code": 200, "ms": 120},
            {"name": "SEC XBRL", "purpose": "US fundamentals", "ok": False, "code": 403, "ms": 90},
        ]
    }
    html = rd._api_health(status)
    assert "1/2 sources up" in html
    assert "Yahoo/yfinance" in html and "✅" in html and "🔴" in html and "403" in html


def test_challenges_flag_down_apis():
    metrics = {"gov_fail": [], "todo": 0}
    status = {"api_health": [{"name": "SEC XBRL", "ok": False}, {"name": "Yahoo", "ok": True}]}
    out = rd._challenges(["IN"], metrics, status)
    assert "API down: SEC XBRL" in out
