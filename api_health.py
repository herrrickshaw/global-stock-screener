#!/usr/bin/env python3
# api_health.py
# =============
# Best-effort reachability probes for the data-acquisition APIs the screener
# depends on (Yahoo, bhavcopy, SEC, screener.in, Trendlyne, exchange universes,
# news RSS). Feeds the dashboard's 🔌 API Health card so broken sources surface
# every morning.
#
#   python3 api_health.py            # probe + print a table
#
# Pure/offline-safe: no network → each endpoint reports ok=False with the error,
# never raises. Probes run in parallel with a short per-call timeout.
# ⚠️ Research/education only. Not advice.

from __future__ import annotations

import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)

# name -> (purpose, url). HEAD/GET a cheap endpoint per host.
ENDPOINTS: Dict[str, Dict[str, str]] = {
    "Yahoo/yfinance": {
        "purpose": "OHLC history",
        "url": "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=5d&interval=1d",
    },
    "BSE India": {"purpose": "India EOD", "url": "https://www.bseindia.com/"},
    "Stooq": {"purpose": "OHLC fallback", "url": "https://stooq.com/q/d/l/?s=aapl.us&i=d"},
    "SEC XBRL": {
        "purpose": "US fundamentals",
        "url": "https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/Assets.json",
    },
    "screener.in": {"purpose": "India fundamentals", "url": "https://www.screener.in/"},
    "Trendlyne": {"purpose": "DVM / pledge", "url": "https://trendlyne.com/"},
    "SGX": {"purpose": "SG universe", "url": "https://api.sgx.com/securities/v1.1"},
    "Euronext": {"purpose": "EU universe", "url": "https://live.euronext.com/"},
    "Eastmoney": {
        "purpose": "CN universe",
        "url": "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=1&fs=m:1",
    },
    "Moneycontrol RSS": {"purpose": "News", "url": "https://www.moneycontrol.com/rss/business.xml"},
}


def _probe_one(name: str, purpose: str, url: str, timeout: int) -> dict:
    t = time.time()
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "From": "screener@example.com"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(256)
            return {
                "name": name,
                "purpose": purpose,
                "ok": True,
                "code": r.status,
                "ms": int((time.time() - t) * 1000),
            }
    except Exception as e:  # noqa: BLE001
        code = getattr(e, "code", "")
        return {
            "name": name,
            "purpose": purpose,
            "ok": False,
            "code": code,
            "ms": int((time.time() - t) * 1000),
            "error": str(e)[:60],
        }


def probe(timeout: int = 6, max_workers: int = 8) -> List[dict]:
    """Probe all endpoints in parallel; returns a list of result dicts (input order)."""
    items = list(ENDPOINTS.items())
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        results = list(
            ex.map(lambda kv: _probe_one(kv[0], kv[1]["purpose"], kv[1]["url"], timeout), items)
        )
    return results


def summary(results: List[dict]) -> dict:
    ok = sum(1 for r in results if r.get("ok"))
    return {
        "ok": ok,
        "total": len(results),
        "down": [r["name"] for r in results if not r.get("ok")],
    }


def main() -> int:
    res = probe()
    s = summary(res)
    print(f"API health: {s['ok']}/{s['total']} up")
    for r in res:
        badge = "OK " if r["ok"] else "ERR"
        print(f"  {badge} {str(r.get('code','')):>3} {r['ms']:>5}ms  {r['name']} ({r['purpose']})")
    return 0 if not s["down"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
