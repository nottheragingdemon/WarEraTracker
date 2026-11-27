# Changelog

Each version is tagged `vX.Y.Z` by the *Release* workflow (Actions → Release → Run workflow, version without the `v`).
To go back to a version: `git checkout vX.Y.Z` (or deploy that tag). The collected history (the `state` branch) is separate and is not rolled back.

## 1.2.2 — 2026-11-27
- **Code health (no visible change):** the collector is split into `wartrack/stages/` (one module per area), with `wartrack/collect.py` re-exporting every stage; a direct test of the exporter's output (shape, packed stats round trip, file split, day aggregates).

## 1.2.1 — 2026-11-27
- **Market tax estimate fix:** the game lists a trade under more than the buyer's country (most likely the seller's too), so trades are now kept per alliance country they are listed under, instead of being filed under the buyer's country (which put many under non-alliance countries). The trades table is rebuilt and backfilled once.

## 1.2.0 — 2026-11-27
- **Company tax tracker:** market tax estimate in the country income section (per day, in the day-by-day table and for every alliance nation): the country's market tax rate × the value of market trades linked to it (7-day average). Clearly marked as an estimate.
- **Collector:** new `trades` stage (market trades for alliance countries, 30 days, incremental with a one-off backfill).
- **Ask WarEra:** `market_trades_days` table.

## 1.1.0 — 2026-11-27
- **Company tax tracker:** country income per day, day by day for the last 30 days (by stream, with the treasury at the end of each day), from new hourly income history.
- **Alerts:** large transfers between alliance nations, a citizen's big donation day, sharp treasury drops (thresholds as repository variables).
- **Ask WarEra:** tables for country income (now and by day) and collector runs.
- **Maintenance:** GitHub Actions on `checkout@v5` and `setup-python@v6` (Node 24); collector dependencies pinned in `requirements-collector.txt`; the HTTP client now comes from async-http-kit 0.4.0 (`asynchttp.aio`) instead of a copy in this repo.

## 1.0.0 — 2026-11-27
First tagged version.
- **Apps:** WarEra Tracker (damage, bounty per 1M damage with daily chart, player card and battle drill-down, player comparison, per-country bar chart, Open-battle links); Company tax tracker (now visible to everyone, with country income per day by stream); EA Money Transfers (transfers tab with sortable list, citizen donations tab with totals, filters and sortable tables); Player efficiency (War / Hybrid / Eco builds, weekly wealth against damage, trend charts, military unit filter, skill-reset markers); Status page; Ask WarEra (testing mode).
- **Collector:** parallel requests through `async_requests.py` (aiohttp); gateway off by default with a cooldown when on; per-stage timings; packed per-battle stats; `ask-data.json` split; MU list every 6 h; closed contracts every 3 h; donations and transfers kept 90 days (one-off donations backfill); 90-day pruning.
- **Alerts:** new and ended battles with links, weekly digest (week over week, efficiency section), failure alerts, skipped-stage notes.
- **Reliability:** weekly database backups with automatic restore fallback, save guard, unit tests and a headless-Chrome page check in CI, stale-data banner, artifact copies built from `site/` by one script.
- **Streamlit:** pages size themselves to their content (`st.iframe`), compact phone cards for long lists, phone navigation keeps the current app in view.
