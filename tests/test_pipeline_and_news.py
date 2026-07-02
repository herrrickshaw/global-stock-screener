# Tests for news_feeds registry, pipeline_status rendering, and orchestrator wiring.
import json

import news_feeds
import pipeline_runner as pr
import repo_dashboard as rd


def test_news_registry_has_all_outlets():
    assert set(news_feeds.FEEDS.keys()) == {"IN", "US"}
    # India: the expanded outlet set
    assert "NDTVProfit" in news_feeds.outlets("IN")
    assert "Moneycontrol" in news_feeds.outlets("IN")
    # US: the expanded outlet set
    for o in ["CNBC", "WSJ", "YahooFinance", "SeekingAlpha", "Nasdaq", "Benzinga"]:
        assert o in news_feeds.outlets("US")
    assert len(news_feeds.feed_urls("IN")) >= 8
    assert len(news_feeds.feed_urls("US")) >= 8


def test_pipeline_execution_card_renders_status():
    status = {
        "generated": "2026-07-02 08:30",
        "data_update": {"ok": True, "detail": "IN +120; serving refreshed"},
        "scans": {"ok": False, "detail": "combined report written for: IN"},
        "pipeline": {"ok": True, "detail": "all tiers populated"},
    }
    html = rd._pipeline_execution(status)
    assert "Data update" in html and "✅" in html
    assert "🔴" in html  # scans failed
    assert "08:30" in html


def test_pipeline_execution_card_empty():
    assert "has not run" in rd._pipeline_execution({})


def test_code_health_card_renders():
    status = {
        "code_health": {
            "lint": {"ok": True, "detail": "ruff + black clean"},
            "tests": {"ok": False, "detail": "1 failed, 200 passed"},
            "governance": {"ok": True, "detail": "governance 6/6; integrity ok"},
            "imports": {"ok": True, "detail": "all modules import"},
        }
    }
    html = rd._code_health(status)
    assert "Lint" in html and "Tests" in html
    assert "🔴" in html  # tests failed


def test_challenges_fold_in_pipeline_and_code_failures():
    metrics = {"gov_fail": [], "todo": 0}
    status = {
        "scans": {"ok": False, "detail": "boom"},
        "code_health": {"tests": {"ok": False, "detail": "1 failed"}},
    }
    out = rd._challenges(["IN"], metrics, status)
    assert "Scans failed" in out
    assert "Tests" in out


def test_news_mood_card_uses_captured(monkeypatch):
    status = {
        "news": {
            "IN": {
                "mood": "POSITIVE",
                "score": 0.36,
                "n_articles": 348,
                "outlet_counts": {"Moneycontrol": 38, "NDTVProfit": 20},
            }
        }
    }
    html = rd._news_mood(["IN"], status)
    assert "POSITIVE" in html and "348" in html and "Moneycontrol" in html


def test_stage_checks_writes_status(tmp_path, monkeypatch):
    # stub the heavy checks so the test is fast + offline
    monkeypatch.setattr(pr, "_check_lint", lambda repo: {"ok": True, "detail": "clean"})
    monkeypatch.setattr(pr, "_check_tests", lambda repo: {"ok": True, "detail": "10 passed"})
    monkeypatch.setattr(pr, "_check_governance", lambda repo: {"ok": True, "detail": "6/6"})
    monkeypatch.setattr(pr, "_check_imports", lambda repo: {"ok": True, "detail": "ok"})
    s = pr.stage_checks(tmp_path, tmp_path)
    saved = json.loads((tmp_path / "pipeline_status.json").read_text())
    assert saved["code_health"]["tests"]["ok"] is True
    assert "generated" in saved
    assert s["code_health"]["lint"]["ok"] is True
