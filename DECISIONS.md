# Decision Register (Architecture Decision Records)

Traceable log of the key design choices behind this repo, why they were made, and
their impact on outcomes. One record per decision. Status: `accepted` · `superseded`
· `proposed` · `rejected`. Parsed by `decisions.py` and surfaced on the dashboard.

Format per record:

- **ADR-NN — Title** `status` (YYYY-MM-DD)
  - **Context** — the forces / problem.
  - **Decision** — what was chosen.
  - **Impact** — effect on the final outcome (what it enabled or cost).
  - **Alternatives** — what was considered and not taken.

---

- **ADR-01 — Tiered memory: LTM (5y) + STM (1y)** `accepted` (2026-07-01)
  - **Context** — 20 markets × thousands of tickers of daily OHLCV is too large to hold hot; most screens need only ~1y while backtests need ~5y.
  - **Decision** — split storage into a long-term memory (5y, year-partitioned parquet, Git LFS) and a derived short-term memory (1y) rebuilt from LTM.
  - **Impact** — screens/serving run on the small STM (fast, cheap); STM is disposable and gitignored, so only LTM is versioned. Enables the whole daily pipeline to stay under a few minutes.
  - **Alternatives** — single flat store (too big to ship); a hosted DB (adds infra + cost, breaks offline-first).

- **ADR-02 — DuckDB query layer over partitioned parquet** `accepted` (2026-07-01)
  - **Context** — need SQL-grade slicing over year-partitioned files without a server.
  - **Decision** — query parquet in place with DuckDB; keep parquet as the source of truth.
  - **Impact** — zero-infra analytical queries; portable to Colab. Cost: DuckDB is an optional dependency, so code paths must degrade when it is absent.
  - **Alternatives** — pandas-only (slower on 5y × thousands of tickers); SQLite (weak columnar/analytics).

- **ADR-03 — Offline-first, best-effort live data** `accepted` (2026-07-01)
  - **Context** — CI must be deterministic; live sources (NSE, Yahoo, RSS) are flaky and rate-limited.
  - **Decision** — every feature has a pure, offline-tested core; live fetches are best-effort and wrapped so failures degrade to a note, never an exception.
  - **Impact** — CI never depends on the network; the daily mailer always sends even on a bad data day. This is the single most load-bearing rule in the repo.
  - **Alternatives** — mock the network in CI (brittle); require live data (non-deterministic CI).

- **ADR-04 — Protected-PR flow with a four-gate CI** `accepted` (2026-07-01)
  - **Context** — solo-maintained repo still needs guardrails against regressions and tampering.
  - **Decision** — no direct pushes to `main`; every change lands via PR gated on lint (ruff+black), pytest matrix (3.10–3.12), integrity checksums, and governance conformance.
  - **Impact** — every merge is green and traceable; enabled ~34 PRs to land safely in one session. Cost: overhead per change (regenerate checksums/dep-map each PR).
  - **Alternatives** — trunk-based direct commits (fast but unsafe).

- **ADR-05 — Executable TOGAF governance (Phase G)** `accepted` (2026-07-02)
  - **Context** — architecture principles are worthless if not enforced.
  - **Decision** — encode principles as `governance.py` checks (integrity, no-secrets, dep-map, tests, CI, docs) that fail the build on breach.
  - **Impact** — principles are continuously verified, not aspirational; surfaced as a KPI on the dashboard.
  - **Alternatives** — a static principles doc (drifts from reality).

- **ADR-06 — SHA-256 integrity manifest** `accepted` (2026-07-02)
  - **Context** — LFS data + code should be tamper-evident and drift-detectable.
  - **Decision** — `integrity.py` writes/verifies `CHECKSUMS.sha256` over tracked files; verified in CI and regenerated pre-commit.
  - **Impact** — any silent change to data or code fails verification. Cost: new tracked files must be staged *before* regenerating (a real bug hit once).
  - **Alternatives** — trust git alone (no content-level drift signal for LFS pointers).

- **ADR-07 — SAFe backlog with WSJF prioritisation** `accepted` (2026-07-02)
  - **Context** — many candidate features; needed an objective build order.
  - **Decision** — `backlog.py` scores items by WSJF = (value+time_criticality+risk)/job_size; PIs pull the top of the ranked list.
  - **Impact** — cleared 21/21 features in a defensible order; backlog state shown on the dashboard.
  - **Alternatives** — ad-hoc/gut ordering (no traceability).

- **ADR-08 — Two-branch topology: `karz` (scans+data) vs `mailer` (dashboard+gates)** `accepted` (2026-07-02)
  - **Context** — the scan stack (`daily_combined_report`, `sentiment_pipeline`) + 121M of market data evolved on `karz`; the dashboard, CI gates, and governance live on `mailer`/`main`.
  - **Decision** — keep them on separate branches; the daily orchestrator bridges them (fetches `pipeline_runner.py`/`news_feeds.py` from `mailer` into the scan tree, copies scan outputs into the dashboard worktree).
  - **Impact** — each stack stays independently testable and gated; the bridge is the price. This shapes every scheduling/pipeline decision.
  - **Alternatives** — one big merge (large, risky, would gate the heavy scan/data on the same CI).

- **ADR-09 — Consolidated single daily email (dashboard is the superset)** `accepted` (2026-07-02)
  - **Context** — separate brief / combined-report / dashboard emails duplicated content.
  - **Decision** — the dashboard embeds the full combined-report fragments (stock picks + street talk + convergence) in its Stock Lists card; one email carries everything.
  - **Impact** — a single morning email, no double-sends; `morning_mailer` demoted to a library helper.
  - **Alternatives** — multiple targeted emails (redundant, noisier inbox).

- **ADR-10 — Combined-report layout as the mailer default** `accepted` (2026-07-02)
  - **Context** — the compact "brief" format lost the detailed pick tables the user relies on.
  - **Decision** — `morning_mailer`/dashboard default to the combined-report layout when fragments exist, falling back to the brief otherwise.
  - **Impact** — restored the familiar per-market picks + talk + convergence; `--format brief` retained as an escape hatch.
  - **Alternatives** — keep the brief default (lost detail).

- **ADR-11 — Expanded news feeds + browser User-Agent** `accepted` (2026-07-02)
  - **Context** — "Talk on the Street" drew on only 4 IN / 2 US outlets; several feeds 403 without a UA.
  - **Decision** — expand to 5 IN / 8 US outlets (validated live) and send a browser UA on every fetch; keep the canonical list in `news_feeds.py`.
  - **Impact** — news pool grew ~229→~348 (IN) and ~140→~285 (US) articles, widening sentiment breadth. Rejected dead feeds (Business Standard, Financial Express, Zeebiz).
  - **Alternatives** — a paid news API (cost, keys); scraping HTML (fragile, ToS risk).

- **ADR-12 — Daily 08:30 orchestrated pipeline, report-and-continue** `accepted` (2026-07-02)
  - **Context** — the report must reflect fresh data and flag its own health without ever going silent.
  - **Decision** — `pipeline_runner.py` runs a scan stage (incremental data update + scans + news) and a checks stage (lint/tests/governance/imports); any step failing is recorded and rendered red, the email still sends.
  - **Impact** — the dashboard self-reports pipeline execution + code flaws; a bad day yields a red-flagged email, not silence.
  - **Alternatives** — abort-on-failure (silent on the days you most need the report).

- **ADR-13 — Dashboard published to a new dated branch each morning** `accepted` (2026-07-02)
  - **Context** — wanted an immutable daily snapshot separate from the code line.
  - **Decision** — each run creates/updates `dashboard/YYYY-MM-DD` off `mailer`, commits the rendered HTML + status JSON, and pushes it.
  - **Impact** — a browsable per-day archive of the report + pipeline status; keeps snapshots out of `main`.
  - **Alternatives** — commit snapshots to `main` (noise); no snapshot (no archive/traceback).

- **ADR-14 — launchd (not cron) for scheduling; SMTP send via `.env`** `accepted` (2026-07-02)
  - **Context** — need a reliable macOS daily trigger; sending needs credentials that must never be committed.
  - **Decision** — a `com.screener.dashboard` launchd agent at 08:30; `send_mailer` reads Gmail app-password only from gitignored `.env`; hardened the runner for unattended git (identity, LFS lock-verify off, push retries).
  - **Impact** — resilient unattended runs; sending stays off until creds are added (branch/snapshot still run). Drafts are created interactively via the Gmail connector, which cannot auto-send.
  - **Alternatives** — cron (weaker macOS integration); hard-coded creds (security breach).

- **ADR-15 — Credentials only in gitignored `.env`; rotate anything exposed** `accepted` (2026-07-01)
  - **Context** — screener.in / Trendlyne / Gmail all need secrets.
  - **Decision** — secrets live only in `.env` (gitignored); a governance no-secrets check scans tracked files; passwords pasted in chat must be rotated.
  - **Impact** — no secret has entered version control; enforced by CI.
  - **Alternatives** — a secrets manager (overkill for a solo local repo).
