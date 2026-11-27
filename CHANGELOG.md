# Changelog

Each version is tagged `vX.Y.Z` by the *Release* workflow (Actions → Release → Run workflow, version without the `v`).
To go back to a version: `git checkout vX.Y.Z` (or deploy that tag). The collected history (the `state` branch) is separate and is not rolled back.

## 1.5.2 — 2026-11-27
- **Fix:** a batch request where some entries failed (HTTP 207, e.g. a company that closed) failed the whole companies stage; now the entries that worked are kept and the failed ones count as missing. This skipped the companies stage at 09:17 once the index had located 19,416 companies in alliance countries.
- **Freshness:** the 15-minute check may be up to 2 hours old before it counts as stale, because GitHub often runs it only hourly at busy times.

## 1.5.1 — 2026-11-27
- **Freshness checks:** every kind of data (16 of them, from the hourly refresh to country income, companies, player snapshots, donations) is checked against how often it should arrive. Stale data shows on the Status page (new *Data freshness* card and a health check) and is posted to Discord once, then every 6 hours, with a note when it recovers. Runs in both the hourly refresh and the 15-minute check, so a missed refresh is caught too. This would have flagged the 1.2.2 income-history bug within about 2.5 hours.

## 1.5.0 — 2026-11-27
- **Company tax tracker:** tax what-if: type other employee or manager income tax rates and see the change per day and month, for the companies shown, all wage tax in the host (the game's figure rescaled) and the host's whole income.
- **Status:** coverage trend: each host's tax coverage over the last 7 days and the overall coverage by day (recorded hourly, kept 90 days).
- **Ask WarEra:** the company data (about 1 MB) loads only when a question needs the companies or wage history table.
- **Fix:** since 1.2.2 the collector couldn't find `scope.json` from its new folder, so the hourly country income history wasn't recorded (other stages fell back to the alliance scope). Fixed, with a test.

## 1.4.1 — 2026-11-27
- **Status:** company coverage per alliance host (staffed companies, workers and wage tax per hour, tracker against the game), the company index's progress, and two health checks for them.
- **Company index:** re-checks only companies outside alliance countries (those inside are re-checked hourly), a thirtieth a day, which cuts the daily lookups from about 43,000 to about 7,600.

## 1.4.0 — 2026-11-27
- **Company tax tracker:** any Emerald Accord country can be the host, and companies of every owner are followed, not only alliance citizens': the source list has the alliance's countries, other countries and **All owners** (which should match the game's totals for the host).
- **Collector:** new daily *Company index* workflow (where every company stands; the API only lists them all together), the hourly companies stage now follows every company in alliance countries (about 6,300), wage history stored per host and owner country with 0.5% change threshold, thinned to 6-hour steps after 48 hours. The company list and wage history live in `company-data.json`, loaded only by the Company page and Ask WarEra, which keeps `data.json` at about 2.3 MB. The company index resumes its full pass across days and only drops companies after a complete pass.

## 1.3.1 — 2026-11-27
- **Company tax tracker fix:** worker counts were 0 for every company because the game's company record stopped listing workers. They now come from `employee.getCompanyEmployees`, so the staff cross-check against the game's region figures works again. Wages and tax were not affected (they come from the wage estimate).

## 1.3.0 — 2026-11-27
- **Guide:** a new page for alliance members explaining every app, how figures such as bounty per 1M damage, builds and the market tax estimate are worked out, the data's limits, the Discord alerts and a glossary.
- **Collector dependencies** install async-http-kit by its `v0.4.0` tag; the Tests workflow also runs when they change.

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
