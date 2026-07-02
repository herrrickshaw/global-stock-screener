#!/usr/bin/env python3
# news_feeds.py
# =============
# Canonical copy of ALL "Talk on the Street" news feeds (kept in sync with the
# scan-side sentiment_pipeline.py), plus a dependency-light market-mood reader so
# the dashboard can show news breadth without importing the full scan stack.
#
# Every function is best-effort/offline-safe: missing feedparser or network just
# yields empty results, never an exception.
# ⚠️ Research/education only. Not advice.

from __future__ import annotations

import socket
from typing import Dict, List, Optional

# Browser UA — several outlets 403 an unidentified client.
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)

# Full registry — mirrors sentiment_pipeline.IndianRSSProvider/USRSSProvider FEEDS.
FEEDS: Dict[str, Dict[str, List[str]]] = {
    "IN": {
        "Moneycontrol": [
            "https://www.moneycontrol.com/rss/business.xml",
            "https://www.moneycontrol.com/rss/results.xml",
            "https://www.moneycontrol.com/rss/marketreports.xml",
            "https://www.moneycontrol.com/rss/economy.xml",
        ],
        "EconomicTimes": [
            "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
            "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
        ],
        "BusinessLine": [
            "https://www.thehindubusinessline.com/markets/feeder/default.rss",
            "https://www.thehindubusinessline.com/companies/feeder/default.rss",
        ],
        "LiveMint": [
            "https://www.livemint.com/rss/markets",
            "https://www.livemint.com/rss/companies",
        ],
        "NDTVProfit": [
            "https://feeds.feedburner.com/ndtvprofit-latest",
        ],
    },
    "US": {
        "CNBC": [
            "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
            "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
            "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
        ],
        "MarketWatch": [
            "https://feeds.content.dowjones.io/public/rss/mw_topstories",
            "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",
            "https://feeds.content.dowjones.io/public/rss/mw_bulletins",
        ],
        "WSJ": [
            "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
        ],
        "YahooFinance": [
            "https://finance.yahoo.com/news/rssindex",
        ],
        "SeekingAlpha": [
            "https://seekingalpha.com/market_currents.xml",
        ],
        "Nasdaq": [
            "https://www.nasdaq.com/feed/rssoutbound?category=Markets",
        ],
        "Benzinga": [
            "https://www.benzinga.com/feed",
        ],
        "Investing": [
            "https://www.investing.com/rss/news_25.rss",
        ],
    },
}


def outlets(market: str) -> List[str]:
    """Outlet names configured for a market."""
    return list(FEEDS.get(market, {}).keys())


def feed_urls(market: str) -> List[str]:
    """Flat list of all feed URLs for a market."""
    return [u for urls in FEEDS.get(market, {}).values() for u in urls]


def market_mood(market: str, timeout: int = 8) -> dict:
    """Best-effort news-breadth + mood for a market.

    Returns {outlet_counts, n_articles, mood, score} or {} if unavailable
    (no feedparser / no network). Mood uses the scan-side scorer when importable,
    otherwise falls back to article counts only (mood="n/a").
    """
    try:
        import feedparser
    except Exception:
        return {}

    socket.setdefaulttimeout(timeout)
    scorer = None
    try:
        from sentiment_pipeline import score_text as scorer  # type: ignore
    except Exception:
        scorer = None

    counts: Dict[str, int] = {}
    scores: List[float] = []
    for outlet, urls in FEEDS.get(market, {}).items():
        for url in urls:
            try:
                d = feedparser.parse(url, agent=UA)
                counts[outlet] = counts.get(outlet, 0) + len(d.entries)
                if scorer:
                    for e in d.entries:
                        s = scorer(f"{e.get('title', '')}. {e.get('summary', '')}")
                        if s:
                            scores.append(s)
            except Exception:
                continue

    n = sum(counts.values())
    if not n:
        return {}
    out = {"outlet_counts": counts, "n_articles": n}
    if scores:
        avg = sum(scores) / len(scores)
        out["score"] = round(avg, 3)
        out["mood"] = "POSITIVE" if avg > 0.05 else "NEGATIVE" if avg < -0.05 else "NEUTRAL"
    else:
        out["score"] = None
        out["mood"] = "n/a"
    return out


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="News-feed registry + market mood")
    ap.add_argument("--market", nargs="*", default=["IN", "US"])
    ap.add_argument("--mood", action="store_true", help="fetch live mood (needs network)")
    a = ap.parse_args(argv)
    for m in a.market:
        print(f"[{m}] outlets: {', '.join(outlets(m))}  ({len(feed_urls(m))} feeds)")
        if a.mood:
            print("  mood:", json.dumps(market_mood(m)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
