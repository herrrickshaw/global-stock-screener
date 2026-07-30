# Changelog

## [Unreleased] — 2026-07-30 — DDD scaffold + IPO tracker duplicates removed

### Removed
- **`src/`** — a dead DDD scaffold (`market_data`/`backtesting`/`reporting`/
  `stock_analysis`/`portfolio_strategy`/`risk_signals`, one incidental
  commit, no adapters, no tests, nothing in this repo or `market-pipeline`
  imported it). Superseded by the real, working DDD implementation now
  living at `market-pipeline/code/python_files/stock_ddd/` in the
  `global-market-research-platform` repo — that's the canonical location
  going forward, not this one.
- **`ipo_tracker.py`** (142 lines) / **`ipo_monitor.py`** (113 lines) —
  duplicates of the canonical, actively-maintained copies in
  `market-pipeline/code/python_files/`. Diffed line-by-line before removal:
  no unique logic beyond the same stale `~/Downloads/...` path defaults
  found in the equivalent duplicates removed from
  `repos/global-market-data`.

See `~/.claude/plans/swift-nibbling-shore.md` (on the machine this repo is
checked out on) for the full architecture-retrofit plan this cleanup was
part of.
