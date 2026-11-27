# Changelog

Each version is tagged `vX.Y.Z` by the *Release* workflow (Actions → Release → Run workflow, version without the `v`).
To go back to a version: `git checkout vX.Y.Z` (or deploy that tag). The collected history (the `state` branch) is separate and is not rolled back.

## 1.0.0 — 2026-11-27
First tagged version.
- **Apps:** WarEra Tracker (damage, bounty per 1M damage with daily chart, player card and battle drill-down, player comparison, per-country bar chart, Open-battle links); Company tax tracker (now visible to everyone, with country income per day by stream); EA Money Transfers (transfers tab with sortable list, citizen donations tab with totals, filters and sortable tables); Player efficiency (War / Hybrid / Eco builds, weekly wealth against damage, trend charts, military unit filter, skill-reset markers); Status page; Ask WarEra (testing mode).
- **Collector:** parallel requests through `async_requests.py` (aiohttp); gateway off by default with a cooldown when on; per-stage timings; packed per-battle stats; `ask-data.json` split; MU list every 6 h; closed contracts every 3 h; donations and transfers kept 90 days (one-off donations backfill); 90-day pruning.
- **Alerts:** new and ended battles with links, weekly digest (week over week, efficiency section), failure alerts, skipped-stage notes.
- **Reliability:** weekly database backups with automatic restore fallback, save guard, unit tests and a headless-Chrome page check in CI, stale-data banner, artifact copies built from `site/` by one script.
- **Streamlit:** pages size themselves to their content (`st.iframe`), compact phone cards for long lists, phone navigation keeps the current app in view.
