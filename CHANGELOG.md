# Changelog

Each version is tagged `vX.Y.Z` by the *Release* workflow (Actions → Release → Run workflow, version without the `v`).
To go back to a version: `git checkout vX.Y.Z` (or deploy that tag). The collected history (the `state` branch) is separate and is not rolled back.

## 2.7.0 — 2026-11-27
- **Tests:** the smoke test also runs every page as the Streamlit app serves it (`--streamlit`) and fails if Battles or Transfers show no numbers (the 2.6.1 bug would now be caught).
- **Data checks:** the Battle check warns once when the site data is missing or empty (per `contract.json`), as well as when it is more than 3 hours old. The back end refuses to publish data that fails the contract, including the part files.
- **Paper:** the cost notes say when the price was last updated and warn when it is more than 3 hours old. The back end freezes a finished month's paper price with its statement, and the month-end Discord post includes the paper to send and its cost at the month's average.
- **Ask WarEra:** the Ask button sits right under the question box; the example questions are below the answer.
- **Back end:** treasury transfers to partners are no longer collected or published (nothing reads them).
- READMEs updated for both repos.

## 2.6.1 — 2026-11-27
- **Fix: Damage tab empty (and donors missing) in the Streamlit app since 2.2.0.** The app inlines the data into each page, but not the new `battle-data.json` / `transfer-data.json`, which the pages then couldn't fetch. The app now inlines them for the pages that use them; a test covers it.

## 2.6.0 — 2026-11-27
- **Balance removed from the tax tracker.** In-game transfers are not always tax payments, so the tracker no longer shows Sent, Balance, Last payment, "still to pay" or OVERDUE. The agreements summary now shows what is owed: this month so far, last month, the total for completed months, and the paper cost. (The back end still records treasury transfers; nothing reads them.)

## 2.5.0 — 2026-11-27
- **Status:** clearer wording ("Last refresh duration / API calls", "Data is 11 min old", "expected within 2.1 days").
- **Player efficiency:** the "Week before" columns only show once there is a week of history (they were rows of dashes); the ranking explanation folds away.
- **Guide:** now covers paper cost, overdue, the Settings preview, the separate collector repo and the data-version banner, and the new problem alerts.
- **Streamlit Settings:** each host has a heading and each partner's settings sit in their own box.

## 2.4.0 — 2026-11-27
- **Tax tracker (with agreements):** a short summary table first (partner, this month, paper cost now, balance); the full partner table and the explanations fold under "How the partner figures are worked out" / "How is this calculated?". The Region and Source filters moved into "More detail", where they apply. A payment ahead of the month is labelled "paid in advance".
- **Phones:** the app tabs fade at the right edge to show they scroll; battle and transfer lists use the compact card layout (about half the height).

## 2.3.2 — 2026-11-27
- Tax tracker: today's paper price is the headline (the summary shows the cost at today's price, with the month-average cost beneath). The agreement statement hides the "Sent by the game" and "keeps" columns when they are zero, and a note says the source/region selectors only filter the detailed view. Phone: wider country labels in the ranking bars.

## 2.3.1 — 2026-11-27
- **Paper price history.** The paper price moves a lot, so the back end now stores samples (at most one per 10 minutes, kept 400 days) and exports each month's average, low and high (`paperMonths`). The statement shows the paper cost at today's price and at the month's average, with the range in the note.

## 2.3.0 — 2026-11-27
- **Paper cost of sending tax.** Sending a tax payment to a partner needs paper equal to the amount × 0.5 (`paperRatio` in the data). The agreement statement now has "Paper to send" and "Cost of the paper" per partner and in total, the copied text includes the totals, and the agreements summary shows the paper for the month so far. The cost uses the market price of paper at the last hourly update (back end collects `itemTrading.getPrices`), so it also moves for finished months.

## 2.2.0 — 2026-11-27
- **Smaller main download.** Battle statistics (`battle-data.json`) and donor lists (`transfer-data.json`) moved out of `data.json`, which drops from about 2.0 MB to 0.7 MB. Only the pages that need them load them (Battles and Ask: battle stats; Transfers: donors).
- **Status:** a "Last 7 days" card (full refreshes, runs with a skipped stage, average and slowest duration, slowest stage and whether it is getting slower).
- Checked: the game's treasury transfers carry no memo or reason, so payments can't be matched to tax agreements beyond treasury transfers to the partner (unchanged).

## 2.1.1 — 2026-11-27
- Settings page: **Check the GitHub token** button (works or not, expiry date, warning under 14 days).
- Back end (separate repo): the monthly restore drill only requires tables every backup has; the first real run found that older backups lack newer tables.

## 2.1.0 — 2026-11-27
- **Stale-data watchdog.** The 15-minute Battle check posts to Discord when `data.json` is more than 3 hours old (once per outage, with a recovery message).
- **Schema number.** The data files carry `schema` (now 4); every page shows a clear banner if the data and page disagree. `site/contract.json` lists the keys the pages need; the back end refuses to publish data that doesn't match it.
- **Tax agreements summary:** the first completed month not yet covered by payments gets a due date, and shows OVERDUE after a week's grace.
- **Settings preview:** before saving, the Streamlit Settings page lists what a change does (rate change with an estimate on the latest month, added or removed partners, regions, start date).

## 2.0.0 — 2026-11-27
- **Split into two repos.** The collector, the history database and its backups, the tax agreements, statements, agreement payments and terms moved to the private repo `WarEraTracker-backend`, with the hourly refresh, company index, weekly backup, weekly digest, statement preview and diagnose workflows. Every hour it publishes `site/*.json` to this repo, so the pages, Streamlit and the artifacts carry on as before.
- **This repo (public)** keeps the pages, the Streamlit app, the artifact sync and a new 15-minute **Battle check** (`scripts/battlecheck.py`, standard library only) that posts new and ended battles to Discord, with its own small state on the `battlecheck-state` branch. The back end no longer posts battle alerts (no duplicates).
- The 15-minute tax-rate sample is gone; rates are checked hourly by the back end. The Status page no longer shows the 15-minute check.
- The Streamlit Settings page saves the agreements to the back-end repo (its `GITHUB_TOKEN` needs access to `WarEraTracker-backend`); without a token it shows the agreements published in data.json.
- **Fix:** since 1.15.0 the main tracker page failed to load ("s.slice is not a function"): the export's start date was overwritten by the agreements' start dates. Fixed in the back end, with a test.

## 1.15.0 — 2026-11-27
- **Payments sent:** the collector keeps every treasury transfer from a host to its agreement partners (`agreement_payments`, including partners outside the alliance, read back 90 days on first run). The tax tracker opens with a *Tax agreements* summary per partner: this month so far, last month, owed for completed months since the agreement's start (`payments_since`), sent, balance (still to pay / settled / paid ahead) and the last payment.
- **Dated terms:** agreement terms are recorded when they change (`agreement_terms`); statements apply the rate and regions in force at each check, so a change doesn't rewrite earlier days.
- **Tax page layout:** with agreements, the summary, statement and month-by-month come first and the detailed tracking folds under *More detail*.
- **Settings page:** an agreement start date per partner.
- **Fix:** the tax tracker's tables had lost their header row since 1.9.0 (a comment swallowed the code that built it).

## 1.14.2 — 2026-11-27
- **Tax agreements:** Ireland pays Mexico 100% and the United Kingdom 90% of the tax generated (the game sends the UK the other 10% from Northern Ireland).

## 1.14.1 — 2026-11-27
- **Tax agreements:** Ireland pays each partner 90% of the tax generated (`pay_percent` per agreement, set on the Settings page), for both the United Kingdom and Mexico. The statement shows tax generated, what Ireland pays, the game's own 10% for a conquered region, and what Ireland keeps; frozen statements store the payment.

## 1.14.0 — 2026-11-27
- **Tax agreements by region:** each agreement now says which of the host's regions it covers: `all`, `core` (the host's original regions) or a list of regions. Ireland ↔ Mexico covers Ireland's core regions; Ireland ↔ United Kingdom covers Northern Ireland only. The collector follows only the companies an agreement covers.
- **Payments, not bills:** with agreements, the month statement is *what Ireland pays each partner*: the tax generated on the partner's citizens' companies in the covered regions, less the 10% the game already sends a conquered region's original country (so the UK gets 90% from Ireland on top of the game's 10%). The page shows the collector's own figures, so the page, the frozen statement and the Discord post agree.
- **Settings page:** per partner, pick the regions covered (core regions, all regions, or chosen regions).
- *Leave out Northern Ireland* only appears when the source country has companies there.

## 1.13.0 — 2026-11-27
- **Company tax tracker:** *Leave out Northern Ireland* option, shown when a single source country other than the United Kingdom is picked with all regions (generally: the host's conquered regions whose original country isn't the source). The figures, history, hour-by-hour and day-by-day tables then cover the rest of the host; the month statement still bills every agreed country in full.

## 1.12.2 — 2026-11-27
- **Company tax tracker:** picking another source country after opening the page shows all of Ireland (the opening view's Northern Ireland only suits the United Kingdom), unless a region was picked by hand. The "keeps a day" card now says the 10% goes to the region's original country, and which region.
- **Tax agreements:** Ireland adds Mexico.

## 1.12.1 — 2026-11-27
- **Faster saves:** the hourly history save compresses with all CPU cores (`xz -T0 -6` instead of single-threaded `-9`), the slowest step of each refresh (about 57 s).
- **Faster companies stage:** wage estimates and employee lists are fetched in one parallel round instead of two.

## 1.12.0 — 2026-11-27
- **Tax agreements:** only source countries with a tax agreement are collected and billed (`agreements.json`; for now Ireland ↔ United Kingdom). The collector follows only companies in agreement hosts owned by agreed countries' citizens; statements, the Discord post and the month-by-month view include agreed countries only. Status no longer measures coverage against the game's country totals while agreements are in force.
- **Streamlit Settings page** (behind the dev key): pick each host's agreed countries and save; it writes `agreements.json` to the repo with a `GITHUB_TOKEN` from the app's Secrets (fine-grained, this repo, Contents read and write).
- **Tax what-if:** the whole-country line scales the game's own figure by the rate change (it no longer depends on tracking every company).
- **Company tax tracker:** opens on Ireland · Northern Ireland · United Kingdom (any can still be changed).
- **Player efficiency:** *Top 20 / Bottom 20* switch (the least efficient players, with their rank in the nation); the collector follows up to 300 players a country (was 100) so the bottom of the 1M+ damage list is covered.

## 1.11.0 — 2026-11-27
- **Statement preview:** a manual *Statement preview* workflow (and `python -m wartrack alerts --statement-preview Ireland`) posts this month's statement so far to Discord, marked as a preview.
- **Company tax tracker:** *Month by month* (each month's tax owed, core-country share and what the host keeps; final where saved, otherwise worked out from history) and *Tax rate history* (every change to the host's employee and manager tax, how long each rate held).
- **Longer history:** the page's wage history now covers 92 days (every check for 48 hours, one per 6 hours to 35 days, then one per day), so earlier months can be looked at.
- **Player efficiency:** *Week before* columns (the same measure and damage for the previous 7 days) and each player's rank change within the nation (↑/↓, or *new*). They fill in once two weeks of daily snapshots exist.
- **Code health:** the pages share one set of helpers in theme.js (elements, cards, KPI tiles, numbers, dates) instead of seven copies.

## 1.10.0 — 2026-11-27
- **Month statements frozen:** on the 1st, the first full refresh saves last month's statement for every alliance host (`statements`, kept permanently), worked out exactly as the page does (checked: same total to the cent). The tax tracker then shows that month as *(final)*. Preview any time with `python -m wartrack statement --host Ireland [--month YYYY-MM]`.
- **Statement on Discord:** the refresh's alert step posts last month's final statement once (hosts by name in `STATEMENT_HOSTS`, default Ireland).
- **Smaller download:** named players' ids in data.json are cut to their last 8 characters (they're only a fallback label), about 300 KB less.
- **Database:** compacted once a week (VACUUM) and its size recorded daily; the Status page shows the size, the last 14 days and the weekly change.
- **Tests:** the Streamlit app is started in CI (menu links present, Ask hidden without the key); a statement test.
- **Streamlit:** the GitHub-link hider uses `st.iframe` (components.html is deprecated).
- **Ask WarEra:** example questions about conquered regions and what original countries receive.
- Status page: the stored-history label reads "Companies (alliance countries)".

## 1.9.0 — 2026-11-27
- **Branding:** the tools are now "WarEra Ireland tools": page and tab titles, the Streamlit tab, Discord failure messages and the weekly digest heading (the Emerald Accord stays where it names the alliance the data covers).
- **Company tax tracker:** a month statement per source country (tax owed, the core-country share, what the host keeps, share of the total) for the chosen host and region, with Download CSV and Copy as text.
- **Storage-full check:** each refresh records whether a company's storage is full (a full company stops producing) and, per host, the tax covered counting all staffed companies against counting producing ones only. The Status page shows both and which is closer to the game's figures over time, to settle the US and Mexico over-count.
- **Speed:** company-data.json is about 30% smaller (region ids and item codes stored once, wages to 4 decimals).
- **Phones:** the tax tracker's wide tables use compact cards (the day or name as the heading, figures in pairs).

## 1.8.0 — 2026-11-27
- **Company tax tracker:** "Received from lost regions" in the country income section: an alliance country's original regions held by another country and the 10% of their tax it receives (e.g. Mexico from Veracruz & Tabasco, held by Guatemala).
- **Company tax tracker:** exact history for one conquered region (recorded per region from today, `wage_snap_reg`); before that it is estimated from today's split, as noted on the page.
- **Correctness:** the game's tax figure for a conquered region is what the holder keeps (90%), and the original country's employee tax already includes its 10% (checked: UK 17.928 + 3.736 = 21.664). The cross-check and the Status coverage now scale conquered regions back up to the full tax, so Ireland reads 97.7% instead of 101.5%.
- **Wording:** "All owners" headings read "all companies" / "active companies" instead of "all owners’ companies".
- **Ask WarEra:** `regions_now` now has held-by and original country, whether conquered, the original country's share per hour, and the game's tax amounts and counts (the old column names called these rates and tracked counts, which was wrong); new `region_wage_history`.
- **Housekeeping:** the two old wage history tables are no longer created and are dropped once nothing in them is within the 35-day history; a headless-Chrome test checks the 90/10 split on the page.
- **Diagnose employees** workflow (manual, read-only): compares employee lists with the game's region counts, to find why the US and Mexico show more workers than the game.

## 1.7.0 — 2026-11-27
- **Company tax tracker:** a region picker after the host country, and conquered regions: the game hands 10% (`conqueredRegionCoreTaxPercent`, read from the game config) of a conquered region's tax to its original country, e.g. the United Kingdom gets 10% of the tax from Northern Ireland, which Ireland holds. Per hour, day by day and the month's bill now show what is passed on and what the host keeps; with the original country as the source, it also shows what that country gets back.
- **Collector:** stores each region's original country and the game's share, and records wage history per host, original country and owner (`wage_snap3`).
- **Games:** a Games section in every menu with links to MapTap and Boreen.
- **Streamlit:** the GitHub links Streamlit Community Cloud adds (Fork and GitHub buttons, the creator badge) are hidden.

## 1.6.0 — 2026-11-27
- **Streamlit:** a fixed menu at the top with one button per app (icon and short name; the current app is highlighted) replaces Streamlit's top or side navigation, and Streamlit's own top bar is hidden, so the pages use the whole screen.

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
